## Context

`save_markdown` (v0.5.0, just shipped) covers the lightweight case: render MD → HTML → POST to Readwise Reader with `category="epub"` as a UI hint. Web research confirmed the official Reader API has no file-upload endpoint and Readwise's own first-party CLI (`@readwise/cli`, March 2025) exposes only `--url` for ingestion. So real EPUB fidelity — TOC, chapter nav, EPUB export from Reader, the experience that feels like a book — requires going around the API entirely.

The one supported path is the **email-to-library** mechanism. Every Reader account has a `<custom>@library.readwise.io` address. Attachments emailed there are ingested as real Library documents. Officially documented, sender whitelist is not required by default. This is the path.

The constraints stack:

1. **No public file API → must use SMTP.** Means a real outbound mail path. The user chose **Resend** as the relay (developer-friendly, simple API key auth, supports custom-domain DKIM).
2. **Pandoc is the only sane MD→EPUB renderer.** Native Python EPUB writers (`ebooklib`, `pypub`) require the caller to build the document tree by hand — chapters, TOC, manifest, spine. Pandoc does all of that in one `--to=epub3` invocation. Costs a ~150MB binary in the container.
3. **Brand fidelity matters.** The user wants the output to look like a CDIT artifact, not a generic pandoc default EPUB. CDIT's visual identity (palette from cdit-works.de: Carbon `#272f38`, Cloud Dancer `#f0eee9`, Strong Blue `#1f5da0`, Mint `#5cc6c3`; typography: Inter Variable for body, League Gothic Variable for display, JetBrains Mono Variable for code) translates into a custom EPUB stylesheet shipped with the tool.
4. **Async ingest is fine.** SMTP delivery to Resend is sub-second; Resend → Readwise → ingest pipeline is "seconds to minutes." The tool returns a send confirmation; the Reader document materializes later. No polling.
5. **Configuration is server-level, not per-call.** `READWISE_LIBRARY_EMAIL`, `RESEND_API_KEY`, `EPUB_FROM_ADDRESS` are env vars loaded at startup. Per-call args stay focused on content + metadata.

## Goals / Non-Goals

**Goals:**
- Single MCP call: markdown in → real EPUB sent to Reader Library, returns send confirmation.
- Brand-consistent EPUB output (CDIT palette, type, accents).
- Configuration model that fits the existing pydantic-settings pattern.
- Zero coupling to Readwise's HTTP API surface — this is a pure SMTP-out tool, doesn't touch `client.py`.
- Graceful degradation: if env vars are missing, `save_markdown_as_epub` raises a clear configuration error; the other 12 tools keep working.

**Non-Goals:**
- Not polling Readwise to confirm ingest. Async means async.
- Not generating cover images automatically. If `cover_image_url` is provided (or in frontmatter), pandoc embeds it; otherwise pandoc generates a default text-only cover with the title + author from the EPUB metadata.
- Not supporting inline image upload. Markdown with `![](relative/path)` won't resolve. Authors must use absolute HTTP(S) URLs; pandoc fetches and embeds those at build time.
- Not exposing pandoc tuning (filters, lua scripts, citation styles, etc.) as parameters. The tool wraps a fixed pandoc invocation. Power users can fork.
- Not supporting EPUB 2 fallback. EPUB 3 only; Reader handles EPUB 3 fine.
- Not implementing a folder watcher. Same out-of-scope answer as before: that's a separate service that calls this tool.
- Not handling more than one attachment per email. One markdown blob, one EPUB, one email.

## Decisions

### D1: Pandoc as a system binary, invoked via `pypandoc`

The renderer is `pandoc --to=epub3 --metadata-file=meta.yaml --css=cdit.css --epub-embed-font=Inter.woff2 [--epub-cover-image=cover.jpg] input.md -o out.epub`. Driven from Python via `pypandoc.convert_text(...)`.

**Alternatives considered:**
- `ebooklib` — pure Python, no system binary. Rejected: caller builds the entire EPUB tree manually (manifest, spine, NCX, TOC, chapters, CSS injection). For markdown input we'd reinvent pandoc's parsing pipeline.
- `pypub` — thin wrapper, similar issue. Rejected.
- Shell out to pandoc directly via `asyncio.create_subprocess_exec` — works but `pypandoc` already handles the temp-file dance, error parsing, and version detection. Marginal preference but accepted.

The ~150MB image-size cost is the price of admission. We're not optimizing for a 50MB Lambda cold-start; the container runs on Komodo as a long-lived service.

### D2: Resend SMTP via `aiosmtplib`, not the Resend HTTP API SDK

Resend offers two paths to send: their HTTP API (which has a Python SDK at `pip install resend`) and a plain SMTP relay (`smtp.resend.com:587`, STARTTLS, username `resend`, password = API key).

We use SMTP because:
1. **Provider-neutral.** If we ever swap to Postmark, AWS SES, or a self-hosted Postfix, the only thing changing is config values. The code stays.
2. **Native async.** `aiosmtplib` is a drop-in async SMTP client that fits the existing event loop. The Resend HTTP SDK is sync; we'd need `asyncio.to_thread` wrapping.
3. **Smaller dep surface.** No vendor SDK pulled in.

`aiosmtplib` (BSD-3, well-maintained, ~300KB) is the standard async SMTP client in the Python ecosystem.

### D3: Brand stylesheet shipped as a static file, tuned for long-form e-reader contexts

The EPUB stylesheet is a small file at `mcp_readwise/assets/epub/cdit-style.css`, baked into the package via Hatchling's `include` and into the Docker image. It applies the CDIT palette but **deliberately diverges from the cdit-works.de typography for the book context**.

A ui-design-brain review caught two book-context errors in an earlier draft:

1. **League Gothic was the wrong display font for chapter headings in long-form EPUB.** On cdit-works.de it's a wordmark moment — set huge, sparingly, as one hero h1. In a 20,000-word document with a chapter break every 1,500 words, the condensed weight-800 tracking-tight setting becomes a tic. AND it wasn't going to be embedded — so on every reader without it (Kobo, most Kindle, etc.) it was silently falling back to Inter weight 800 anyway. **Make the fallback the intention**: drop League Gothic from chapter headings entirely. Inter weight 800 with tighter tracking holds the brand through color and weight contrast (the actual recognizable parts), without the condensed-display fatigue.

2. **Inter body was right but configured wrong.** Default `line-height: 1.65` is fine for screens but tight for sustained reading. Bump to `1.7` and add `text-align: left` (never justify in EPUB — readers' renderers mangle hyphenation).

League Gothic is preserved in the asset set for the **cover plate only** (where pandoc may rasterize it or it can be set on the cover as a one-off display moment), but it never appears in the body stylesheet.

```css
/* Excerpt — full file ships in implementation */
@namespace epub "http://www.idpf.org/2007/ops";

body {
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI",
               Roboto, sans-serif;
  color: #272f38;            /* Carbon */
  background: #f0eee9;       /* Cloud Dancer */
  line-height: 1.7;          /* tuned for long-form */
  text-align: left;          /* never justify in EPUB */
  font-weight: 400;
  hyphens: auto;
}
h1, h2, h3 {
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.15;         /* air around chapter heads */
  color: #272f38;
}
h1 { font-size: 2.2em; border-bottom: 4px solid #1f5da0; padding-bottom: 0.3em; margin-top: 0; }
h2 { font-size: 1.55em; margin-top: 1.8em; }
h3 { font-size: 1.2em; color: #5c5f66; margin-top: 1.4em; }
a, a:visited { color: #1f5da0; text-decoration: underline; text-underline-offset: 3px; }
blockquote {
  border-left: 4px solid #5cc6c3;   /* Mint accent */
  padding-left: 1em;
  color: #5c5f66;                   /* Carbon muted */
  font-style: italic;
}
code, pre {
  font-family: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
  background: rgba(197, 192, 208, 0.18);  /* Lavender Blue, faded */
  font-size: 0.9em;
}
pre { padding: 1em; border-left: 3px solid #1f5da0; overflow-x: auto; }
.eyebrow {
  font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.22em;
  font-weight: 700; color: #5c5f66;
}
```

**Reader compatibility**: Readwise's Reader supports modern EPUB3 CSS (most CSS3, hex colors, web-safe fonts). Hex colors > OKLCH for EPUB context — OKLCH support across e-reader pipelines is uneven, and the brand identity translates cleanly to hex (Carbon `#272f38`, Cloud Dancer `#f0eee9`, Strong Blue `#1f5da0`, Mint `#5cc6c3`).

**Font embedding strategy: static woff2 subsets, not variable.** EPUB reader support for `woff2-variations` is uneven across Kobo, older Kindle, and Boox firmware — some silently fall back, some mis-render glyph widths. Shipping three static woff2 files (Inter 400, 700, 800; latin + latin-ext subsets) costs maybe 20–30KB more than one variable file but gets predictable rendering on every device. Variable fonts are a web optimization; EPUB is a static artifact distributed across a fragmented runtime — pick the boring win.

- **Embed**: Inter 400 + Inter 700 + Inter 800, latin + latin-ext, woff2 static subsets. Estimated ~110–140KB total.
- **Do not embed**: League Gothic (not used in body), JetBrains Mono (rare in user content; system mono fallback is fine).
- **Latin-ext range** is required for German (umlauts in user content) and other extended-latin scripts.

**Alternatives considered (this round):**
- Replace Inter body with Literata / Source Serif / Atkinson Hyperlegible for better long-form readability. Rejected — readability delta is small (~5–10% perceived comfort on e-ink), and dropping Inter would discard the only thing that makes this artifact recognizably CDIT rather than generic pandoc default. **Brand wins on body** (recognition compounds across pages); readability wins on display (where wrong fonts create active friction every chapter).
- Embed both Inter and League Gothic. Rejected — even if embedded, League Gothic for every chapter heading is fatiguing in book context, and the +80KB cost buys an outcome we'd want to design *away* from.
- Variable Inter (single file). Rejected — see above. Predictable static subsets win in fragmented EPUB runtime.

**Alternatives considered (earlier round):**
- Hard-code CSS as a Python string literal. Rejected: brand changes would require code edits, not asset edits.
- Generate CSS from a Python theme dict. Rejected: overengineered. Brand iteration happens in CSS, not Python.

### D4: EPUB metadata YAML built per-call; identifier is caller-controllable

Pandoc accepts a `--metadata-file` pointing to a YAML doc that fills the EPUB's OPF manifest (title, author, language, publisher, date, identifier, rights). We build this on the fly:

```yaml
---
title: "{resolved title}"
creator: "{resolved author or 'Casey Romkes'}"
language: en
date: "{published_date or today}"
publisher: "CDiT Works"
identifier:
  - scheme: {scheme}        # "uuid" or "x-mcp-readwise-idempotency"
    text: "{identifier}"    # uuid4() if no idempotency_key, else "epub-key-<key>"
rights: "© {year} {creator}"
description: "{summary or ''}"
subject: {tags as YAML list}
---
```

**Identifier resolution:**

1. If the caller provides `idempotency_key` (any string), the `dc:identifier` becomes `epub-key-<idempotency_key>` with scheme `x-mcp-readwise-idempotency`. Two sends with the same key produce EPUBs with the same identifier. Readwise's ingest pipeline treats matching identifiers as the same logical document and updates in place rather than duplicating.
2. If no `idempotency_key` is provided, the identifier is a fresh `uuid4()` with scheme `uuid`. Behaves like the prior design — each call produces a unique entry.

**Why this matters (ux-auditor finding):** LLM agents in production retry on transient failures. If a session crashes between pandoc completing and the agent reading `EpubSendResult`, the retry creates a duplicate Library entry. A caller-supplied `idempotency_key` (computed from e.g. SHA-256 of `(title + body)`) closes this class of failure entirely without requiring any server-side dedup store.

**Why not auto-derive the key from content hash?** Because that's a hidden contract: identical markdown content with different intended-uses (drafting iterations, scheduled re-sends, A/B versions) would silently collapse. Making the key explicit puts dedup in the caller's hands. The docstring guides usage — "pass a stable string if you want retries to dedupe; omit for one-shot semantics."

### D5: Cover image strategy

Three branches:

1. **`cover_image_url` parameter (or frontmatter `image_url`) provided**: pandoc downloads and embeds via `--epub-cover-image=<downloaded-path>`. Tool does the download (httpx) to a temp file, passes the local path. Validates content-type is image/*.
2. **No cover URL provided**: pandoc generates a default text-only cover from EPUB metadata (title + author). Acceptable for notes/drafts.
3. **`generate_cover=True` parameter (deferred)**: future enhancement — could call a CDIT brand template that overlays title text on a brand-colored background. Not in v1.

**Alternatives considered:** auto-grabbing the first inline image. Rejected: surprising, brittle, and not a good cover at thumbnail size.

### D6: Async send returns send confirmation, not ReaderDocument; recipient returned in full

```python
class EpubSendResult(BaseModel):
    success: bool
    accepted_at: str   # ISO 8601 — pass this as `since` to verify_epub_received
    recipient: str     # full address, e.g. "casey-personal@library.readwise.io"
    message_id: str    # SMTP-assigned, from server response
    file_size_bytes: int
    title: str         # resolved title — pass this to verify_epub_received
    location: str      # the location param the caller passed (informational)
    identifier_scheme: str   # "uuid" or "x-mcp-readwise-idempotency"
    note: str          # leads with the async contract: "Sent. Document appears in 1–5 minutes."
```

Returning a `ReaderDocument` would lie — the document doesn't exist yet. A dedicated result model makes the async contract explicit.

**Recipient returned in full, not masked** (revised from earlier draft per ux-auditor finding): The earlier design masked the recipient to `c***@library.readwise.io` reasoning that library emails are bearer-credentials. But:

1. The LLM doesn't need this value to do its job — it has nothing actionable to do with it. Masking it doesn't reduce LLM-side risk.
2. The human reading the transcript DOES need the full address when ingest silently fails and they need to verify "did the right address get the email?" Masking degrades debugging.
3. The threat model "transcript logs leak" is real but if logs leak, the env var (or 1Password reference) on the host is the bigger exposure.

Return the full recipient. Document the bearer-credential nature in README under "Setup." For paranoid deployments, the user controls their `READWISE_LIBRARY_EMAIL` env var and can rotate the address via Readwise settings if it leaks.

The `title` and `accepted_at` fields are intentionally shaped to feed directly into `verify_epub_received(title=..., since=...)` — the LLM can chain the two tools without any field-name mapping.

### D7: Configuration loaded at startup, validated lazily; docstring leads with requirements

The three new env vars (`READWISE_LIBRARY_EMAIL`, `RESEND_API_KEY`, `EPUB_FROM_ADDRESS`) live in `Settings` with empty-string defaults (`str = ""` for non-secrets; `SecretStr = SecretStr("")` for the API key) — matching the existing `Settings` style for `readwise_token` and `mcp_api_key`. Server boot succeeds without them. The first call to `save_markdown_as_epub` checks them via the `epub_sender_configured` property and raises a clear `ConfigurationError` if any is missing.

This is the same lazy-validation pattern `MCP_API_KEY` follows for stdio mode (only required when `TRANSPORT=http`). Lets users adopt the new tool incrementally without forcing existing deployments to set unused env vars.

**The tool's docstring leads with the requirements** (revised per ux-auditor finding), e.g.:

```
async def save_markdown_as_epub(...) -> EpubSendResult:
    """ASYNC: Returns after SMTP delivery. Document appears in Reader in 1–5 minutes.
    Do not tell the human the document is available until verify_epub_received confirms it.

    REQUIRES env vars: READWISE_LIBRARY_EMAIL, RESEND_API_KEY, EPUB_FROM_ADDRESS.
    If unconfigured, raises ConfigurationError immediately.

    Renders markdown to a real EPUB 3 via pandoc with CDIT brand styling, then
    emails it to the user's Readwise Library email through a Resend SMTP relay.
    ...
    """
```

LLM agents that read this lead before calling can:
1. Pre-flight check by surfacing the requirements to the human if config is missing
2. Set the right async expectation with the human before saying "done"
3. Chain `verify_epub_received` immediately or schedule a follow-up confirmation

This level of directness in a docstring (imperative voice, "do not tell the user…") is unusual for human-consumed APIs but appropriate for an LLM-consumed surface where the docstring IS the contract.

`/health` exposes:

```json
"epub_sender": {
  "configured": true,
  "smtp_host": "smtp.resend.com",
  "smtp_port": 587,
  "from_address": "mcp-readwise@cdit-dev.de",
  "library_email_set": true
}
```

(Note: `library_email_set` is a boolean only — `/health` is a public-ish unauthenticated endpoint, so we don't put the library email there. The tool's `EpubSendResult.recipient` does return the full address — different threat model, different surface. The from_address is fine to expose in `/health` because it's public-facing in any sent mail.)

### D8: Error handling and retries

Three failure modes worth distinguishing:

1. **Pandoc invocation failed.** Bad markdown, missing binary, OOM. `pypandoc` raises; we surface as `EpubGenerationError` with the pandoc stderr trimmed to 500 chars.
2. **SMTP delivery to Resend failed.** Network, auth, rate limit, malformed message. `aiosmtplib.SMTPException`; we retry once with exponential backoff (1s then 4s), then surface as `SmtpDeliveryError` with the server response code.
3. **Resend accepted, Readwise pipeline silently failed.** Out of band. We don't know about it. Documented as a known limitation; the user notices when the document doesn't appear in Reader.

Resend's own delivery retry semantics handle most transient failures on their side. Our 2-attempt retry budget is for client-side transients (TLS handshake, connection reset). Beyond that, surfacing the error to the caller is right — they can retry the MCP call.

### D9 (revised): Location param accepted, informational-only

`save_markdown` accepts a `location` Literal (`new` / `later` / `shortlist` / `archive`) and forwards it to Readwise's API. The email-to-library pipeline has no equivalent — Readwise email-ingested documents always land in the default Library state.

We accept `location` on `save_markdown_as_epub` anyway, for two reasons:

1. **Parity** — LLM agents using `save_markdown` and switching to `save_markdown_as_epub` won't trip on a different signature.
2. **Chaining** — the param is echoed into `EpubSendResult.location` so the LLM has clear hand-off material for a follow-up move call after `verify_epub_received` confirms the document.

The docstring documents this honestly: "Accepted for parity with `save_markdown`, but the email-to-library pipeline only places documents in the default Library state. To route to `later` / `shortlist` / `archive`, follow this call with `verify_epub_received` to get the document_id, then call the appropriate move tool." We do NOT silently lie or attempt to route via subject-line tricks.

### D10: verify_epub_received as a sibling tool, not a sub-feature

```python
class VerifyResult(BaseModel):
    found: bool
    document: Optional[ReaderDocument]  # populated when found
    note: str   # LLM-readable guidance: "Found." / "Not yet — retry in 1–2 minutes." / "Likely failed — N minutes since send."

async def verify_epub_received(
    title: str,
    since: str,         # ISO 8601 — pass EpubSendResult.accepted_at verbatim
    fuzzy: bool = True, # case-insensitive contains match by default
) -> VerifyResult: ...
```

Implementation: wraps `mcp_readwise.tools.reader.list_documents` (the internal function, still importable even though it's no longer registered as an MCP tool post-v0.4.0). Filters by `category="epub"`, `updated_after=since`, then matches the document title against the provided title (case-insensitive contains by default). Returns the first match or `found=False`.

The `note` field is the load-bearing piece — it embeds time-aware guidance the LLM uses to decide whether to retry:

| Elapsed since `since` | `found` | `note` content                                                              |
|-----------------------|---------|-----------------------------------------------------------------------------|
| < 60s                 | false   | "Too early — Readwise typically ingests within 1–5 minutes. Retry shortly." |
| 60s – 5min            | false   | "Not yet — ingest pending. Retry in 1–2 minutes."                           |
| 5min – 15min          | false   | "Late — Readwise ingest usually completes by 5 min. May have failed."        |
| > 15min               | false   | "Not found — check SMTP delivery (Resend dashboard) and library email."     |
| any                   | true    | "Found in Reader Library."                                                  |

**Why a sibling tool rather than baking it into `save_markdown_as_epub` as a `wait_for_ingest=True` flag:**

1. Blocking-and-polling inside the send tool would force a sync contract on an inherently async pipeline — defeats the purpose of the email path.
2. The LLM controls when to verify based on conversation flow ("user asked is it there yet?" → call verify; "send and move on" → don't call verify).
3. A standalone verify is reusable: useful even when the EPUB was sent in a previous session, and useful for diagnosing arbitrary library-email-ingested documents.

`/health` `tools` count goes from 12 → 14 (two new tools, not one).

### D11: File-size guardrails

EPUB output for a typical 5000-word markdown doc is ~50–150KB. With Inter embedded, +170KB. With an embedded cover image, +50–500KB. So real-world EPUBs from this tool are well under 2 MB; the ceiling is a guardrail against pathological inputs (500-page markdown with 200 embedded images via URL), not a normal-case constraint.

The wire-side limits stack:

- **Resend**: 40 MB max email size *after* base64 encoding.
- **Readwise email-to-library ingest**: 30 MB max email size (binding constraint — tighter than Resend).
- **Base64 inflation**: ~33% on the binary attachment portion.
- **MIME overhead**: ~1 MB for headers, multipart boundaries, body text.

Working backwards from Readwise's 30 MB cap: `(30 - 1) / 1.33 ≈ 21.8 MB` raw binary fits. We set the ceiling at **20 MiB = 20,971,520 bytes** for margin. EPUBs over that raise `EpubTooLargeError` before the SMTP send.

## Risks / Trade-offs

- **[Pandoc binary in image]** → Adds ~150MB to the Docker image. Mitigation: accepted as cost of admission; document in README; future optimization could move EPUB generation to a separate sidecar service if image size becomes an operational pain.
- **[Async ingest with no callback]** → Caller can't programmatically confirm the document landed. Mitigation: document prominently; the tool's docstring leads with this; future work could add a `verify_epub_landed(title, since=...)` companion tool that polls `reading_status`.
- **[Resend free-tier rate limits]** → 100 emails/day on Resend's free tier; 3000/month on $0 dev plan. Mitigation: document in README; for high-volume usage the user can upgrade or swap SMTP provider via the `SMTP_HOST`/`SMTP_PORT` settings.
- **[Library email is a bearer credential]** → Anyone who gets the address can spam the user's Reader Library. Mitigation: never log it, never include in /health output as plaintext, mask in tool responses. The address itself stays in env vars (or 1Password service worker → Komodo variable in prod).
- **[Brand stylesheet ages]** → If cdit-works.de redesigns, the EPUB output drifts from current brand. Mitigation: brand sheet is a single CSS file; updates are a one-line PR. Document the source-of-truth relationship (cdit-works.de CSS variables → this file).
- **[Frontmatter `image_url` triggers a network fetch]** → Adds latency and a failure mode. Mitigation: 10s timeout on cover fetch; if it fails, fall back to pandoc's default cover instead of erroring out.
- **[Two tools that look similar]** → Users may confuse `save_markdown` and `save_markdown_as_epub`. Mitigation: tool docstrings explicitly state the trade-off (sync vs async, HTML-as-epub-UX vs real-EPUB-via-email); README has a side-by-side decision table.

## Migration Plan

No migration. Purely additive:

1. Add deps (`pypandoc`, `aiosmtplib`) and pandoc system binary to Dockerfile.
2. Ship the new modules (`tools/epub_sender.py`, `tools/epub_verifier.py`, `epub_render.py`, `smtp_client.py`) + brand CSS asset + static font subsets.
3. Bump server `/health.tools` to 14 (two new tools: `save_markdown_as_epub` and `verify_epub_received`).
4. Document env var setup in README.

Rollback: revert the commit. The new tools are gated by env vars — if the rollback misses anything, `save_markdown_as_epub` just refuses to run with a configuration error, and `verify_epub_received` falls back to "Not found" since there's nothing to find.

## Open Questions

- **Should there be a per-call override for the brand CSS?** A `style="minimal" | "branded" | "custom-css-string"` parameter. Deferred — premature. v1 is one branded style.
- **Resend webhook integration** to know when Readwise actually ingested? Resend offers webhooks on email events (delivered/bounced). `verify_epub_received` already covers the LLM-side observability need; webhook integration would be useful for autonomous workflows but is deferred — out of scope.
- **Should `verify_epub_received` block-and-wait** with internal polling for up to N seconds, vs the LLM-driven manual retry pattern? Current design is non-blocking single-shot. Blocking would be friendlier for autonomous agents but uses tool-call budget. Worth revisiting after we see real usage patterns.

**Resolved (folded into design above, no longer open):**
- ~~Font embedding scope~~ → static woff2 subsets, Inter 400 + 700 + 800, latin + latin-ext (D3).
- ~~League Gothic role~~ → cover plate only, not body headings (D3, ui-design-brain finding).
- ~~Retry footgun on UUID-per-call~~ → caller-supplied `idempotency_key` becomes `dc:identifier` when provided (D4, ux-auditor finding).
- ~~Recipient masking trade-off~~ → return full address; LLM doesn't need it but humans debugging do (D6, ux-auditor finding).
- ~~Companion verify tool~~ → ship `verify_epub_received` in the same change as a sibling MCP tool (D10, ux-auditor finding).
