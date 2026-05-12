## Why

The just-shipped `save_markdown` tool gets owned content into Readwise Reader, but only as HTML hinted at `category="epub"`. A research pass confirmed that even Readwise's own official CLI (released March 2025) has no file-upload command — the public API simply has no way to ingest a real EPUB binary. The one supported path for *actual* EPUB ingestion is the email-to-library mechanism: every Reader account has a `<custom>@library.readwise.io` address that accepts EPUB attachments and ingests them with real TOC, chapter navigation, and downloadable EPUB export from Reader. Hitting this from an MCP tool unlocks the original vision the user sketched: "drop markdown in, get a real book-shaped artifact in your reading queue."

## What Changes

### New tools (additive)

- **NEW** `save_markdown_as_epub(markdown, title=None, author=None, summary=None, tags=None, note=None, cover_image_url=None, published_date=None, idempotency_key=None) → EpubSendResult`
  - Accepts a markdown string (or one with YAML frontmatter, same parser as `save_markdown`)
  - Renders markdown → EPUB binary via pandoc, with a metadata block (title, author, lang, date, cover-image if provided)
  - Sends the EPUB as an email attachment via Resend SMTP relay to the user's configured `<custom>@library.readwise.io` address
  - Returns immediately with an `EpubSendResult` (success, accepted_at, recipient, message_id, file_size_bytes, title, note) — does NOT wait for Readwise ingest, which can take seconds to minutes asynchronously
  - Does NOT return a `ReaderDocument` (unlike `save_markdown` and `save_url`) because Readwise's email pipeline is async and doesn't echo back the resulting document ID
  - `note` parameter parity with `save_markdown` — attached as EPUB metadata description supplement and a "From the author" preface block
  - `idempotency_key` parameter — when provided, used as the EPUB `dc:identifier` so retries with the same key collapse into one Library entry; when omitted, a fresh UUID v4 is generated per call. Closes the LLM-agent retry footgun where a crashed/retried call would otherwise duplicate
  - Docstring leads with the async contract loudly, so LLM agents set the right expectations with the human before calling

- **NEW** `verify_epub_received(title, since, fuzzy=True) → VerifyResult`
  - Companion confirmation tool — wraps the internal `list_documents` to check whether a recently-sent EPUB has landed
  - Use after `save_markdown_as_epub` returns: pass the resolved `title` and the `accepted_at` timestamp from `EpubSendResult` as `since`
  - Returns `VerifyResult(found: bool, document: Optional[ReaderDocument], note: str)` — `note` guides the LLM on whether to retry ("Not yet — Readwise ingest can take up to 5 minutes; retry in a minute") or report success
  - Cheap to ship (~30 lines of code, one HTTP call) and closes the dead-end where the human asks "is it there yet?" with no programmatic answer

### Dependencies

- Add `pypandoc>=1.13` (Python wrapper) to `pyproject.toml`
- Add pandoc system binary to the Docker image (~150MB; install via `apt-get install pandoc` in the Dockerfile)
- Add `aiosmtplib>=3.0` for async SMTP send (httpx-style fit with the existing async event loop)
- No Resend SDK — Resend's SMTP relay is a standard SMTP server (`smtp.resend.com:587`, STARTTLS, username `resend`, password = API key); a plain SMTP client is the right interface and avoids tying the implementation to one provider
- **Static font subsets** committed to the repo (not generated at build): Inter weight 400, 700, 800, latin + latin-ext woff2 files at `mcp_readwise/assets/epub/fonts/`. Static rather than variable because EPUB reader support for woff2-variations is uneven across Kobo, older Kindle, and Boox firmware — picking static trades ~20–30KB for predictable rendering on every device

### Configuration (new settings)

- `READWISE_LIBRARY_EMAIL` — required, the user's `<custom>@library.readwise.io` address
- `RESEND_API_KEY` — required, the Resend API key used as SMTP password (SecretStr)
- `EPUB_FROM_ADDRESS` — required, the verified sender address registered in Resend (the user's own domain, e.g. `mcp-readwise@cdit.de`)
- `SMTP_HOST` — default `smtp.resend.com` (override to swap providers)
- `SMTP_PORT` — default `587`
- `EPUB_LANG` — default `en` (used in EPUB metadata; can be overridden per call later if needed)

### Hygiene

- `/health` `tools` count goes from 12 → 14 (two new tools: `save_markdown_as_epub` + `verify_epub_received`)
- `/health` exposes a new `epub_sender` block with `configured: bool` (true only if all three required env vars are set)
- Version bumps to `0.6.0` (additive minor)
- README gets a `save_markdown_as_epub` section documenting the Resend + library-email setup, and a side-by-side decision table vs `save_markdown` so callers (LLMs and humans) pick the right tool

## Capabilities

### New Capabilities

- **`save-as-epub`**: A pair of tools (`save_markdown_as_epub` + `verify_epub_received`) that together cover the async EPUB delivery flow. `save_markdown_as_epub` turns a markdown document into a real EPUB (via pandoc) and delivers it to Readwise Reader's Library by emailing it as an attachment to the user's `@library.readwise.io` address through a Resend SMTP relay. `verify_epub_received` confirms ingest by checking the Reader document list for a matching title since the send timestamp. Together they cover: markdown-to-EPUB conversion (with metadata frontmatter support, `note` parity with `save_markdown`, `idempotency_key` for retry-safe dedup), the SMTP delivery contract (sender domain, attachment encoding, message structure), the configuration model (three required env vars), the async return semantics (success means "handed to SMTP," not "visible in Reader"), and the post-send confirmation flow.

### Modified Capabilities

None. The `save-markdown` capability (just-shipped sibling) is unaffected; both tools remain registered and serve different fidelity tiers.

## Impact

- **Code**: One new tool module (`mcp_readwise/tools/epub_sender.py`), one new helper (`mcp_readwise/epub_render.py` for pandoc invocation), one new transport module (`mcp_readwise/smtp_client.py` for the async send), new Pydantic config fields, server.py registration, README section. Reuses the existing `mcp_readwise/markdown_render.py` for frontmatter parsing and metadata resolution.
- **Dependencies**: `pypandoc`, `aiosmtplib`. Pandoc system binary in the Docker image (~150MB on the slim variant).
- **Container**: Image size grows by ~150MB. Acceptable — pandoc is the single shared binary that handles arbitrary markdown extensions, real metadata, cover image embedding, and EPUB3 output.
- **External services**: Adds a hard dependency on Resend for SMTP and on the user having a verified sender domain in Resend. Without `RESEND_API_KEY` and `EPUB_FROM_ADDRESS` set, the tool returns a configuration error at call time (not at startup, so `save_markdown` and the other 11 tools keep working).
- **Security**: Resend API key is a SecretStr loaded from env (1Password service worker in production via Komodo variable injection). The library email address is config-time, not user-supplied per call, so there is no inbound email-injection surface. Attachment is signed only by Resend's DKIM (handled by Resend) — Readwise treats the address as a trusted shared secret.
- **Async semantics**: This tool breaks the synchronous contract every other Reader-write tool has (`save_url`, `save_markdown` both return a populated `ReaderDocument`). Documented prominently in the tool's docstring leading line so LLM agents set expectations with the human before calling. Callers that need synchronous confirmation should invoke `verify_epub_received` (the companion tool shipped alongside) one to five minutes after the send.
- **Location parameter**: `location` accepted as a param for parity with `save_markdown` but documented as informational-only — the Readwise email-to-library pipeline always lands documents in the default Library state. Callers wanting to route to `later` / `shortlist` / `archive` must follow up with a separate move call. The param is preserved on `EpubSendResult` so the LLM can chain that follow-up reliably.
- **Out of scope**: Folder watcher (still a separate downstream service), MD file path inputs (string content only), inline image upload (`![](./local.png)` requires absolute URLs in markdown; pandoc will embed remote images during EPUB build but local paths are caller-resolved). Retry-on-failure beyond aiosmtplib's defaults (acceptable since SMTP delivery to Resend is reliable; if it fails the tool surfaces the error and the caller retries).
