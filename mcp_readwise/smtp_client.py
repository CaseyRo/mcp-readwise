"""Async SMTP delivery for EPUB attachments.

Provider-neutral: defaults to Resend (`smtp.resend.com:587`, STARTTLS,
username `resend`, password = API key), but `SMTP_HOST` / `SMTP_PORT`
overrides let the same code work against Postmark, AWS SES, or any
RFC-5321-compliant relay.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid

import aiosmtplib

from mcp_readwise.config import settings

logger = logging.getLogger(__name__)

_RETRY_DELAYS_SECONDS = (1.0, 4.0)
_AUTH_FAILURE_CODES = (535, 530)


class SmtpDeliveryError(RuntimeError):
    """Raised when SMTP delivery fails after retry budget is exhausted."""


@dataclass
class SendResult:
    message_id: str
    accepted_at: str
    server_response: str


def _build_message(
    from_addr: str,
    to_addr: str,
    subject: str,
    body_text: str,
    epub_bytes: bytes,
    filename: str,
) -> EmailMessage:
    """Construct a MIME message with the EPUB as a base64 attachment."""
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    # Assign a real, deliberate Message-ID so the id we report back is the
    # actual header on the wire (searchable in the Resend dashboard), not a
    # locally-fabricated UUID that masquerades as a provider id (CDI-1311).
    domain = from_addr.rsplit("@", 1)[-1] if "@" in from_addr else None
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(body_text)
    msg.add_attachment(
        epub_bytes,
        maintype="application",
        subtype="epub+zip",
        filename=filename,
    )
    return msg


def _is_transient(code: int | None) -> bool:
    """4xx codes are transient; retry. 5xx (especially auth) are not."""
    if code is None:
        return True  # connection error with no code → transient
    if code in _AUTH_FAILURE_CODES:
        return False
    return 400 <= code < 500


async def send_epub(
    from_addr: str,
    to_addr: str,
    subject: str,
    body_text: str,
    epub_bytes: bytes,
    filename: str,
) -> SendResult:
    """Send the EPUB as an email attachment.

    Retries once on transient (4xx) errors with exponential backoff
    (1s, then 4s). Auth and other 5xx errors surface immediately.
    """
    msg = _build_message(from_addr, to_addr, subject, body_text, epub_bytes, filename)
    password = settings.resend_api_key.get_secret_value()

    last_error: Exception | None = None
    for attempt, delay in enumerate([0.0, *_RETRY_DELAYS_SECONDS]):
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            errors, response = await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                start_tls=True,
                username="resend",
                password=password,
            )
            # `aiosmtplib.send` returns a per-recipient `errors` dict for
            # recipients the relay refused without raising (partial failures).
            # The library email is our only recipient, so a non-empty dict
            # means the message was NOT accepted for delivery — surfacing
            # `success` on that would be a false positive (CDI-1311 Defect 1).
            if errors:
                refused = ", ".join(sorted(errors)) or "unknown recipient(s)"
                raise SmtpDeliveryError(
                    f"SMTP relay refused delivery to: {refused}"
                )
            message_id = msg.get("Message-ID", "") or str(uuid.uuid4())
            return SendResult(
                message_id=message_id.strip("<>"),
                accepted_at=datetime.now(timezone.utc).isoformat(),
                server_response=str(response or "accepted"),
            )
        except aiosmtplib.SMTPResponseException as exc:
            last_error = exc
            if not _is_transient(exc.code):
                raise SmtpDeliveryError(
                    f"SMTP {exc.code} {exc.message}"
                ) from exc
            logger.warning(
                "SMTP transient error (attempt %d): %s %s",
                attempt + 1,
                exc.code,
                exc.message,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            last_error = exc
            logger.warning(
                "SMTP connection error (attempt %d): %s", attempt + 1, exc
            )

    raise SmtpDeliveryError(
        f"SMTP delivery failed after {len(_RETRY_DELAYS_SECONDS) + 1} attempts: "
        f"{last_error}"
    )
