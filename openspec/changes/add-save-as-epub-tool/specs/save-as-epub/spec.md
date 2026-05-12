## ADDED Requirements

### Requirement: save_markdown_as_epub tool converts markdown to EPUB and emails it to Readwise Library

The MCP server SHALL expose a `save_markdown_as_epub` tool that accepts a markdown string, renders it to an EPUB 3 binary via pandoc, and delivers it as an email attachment to the configured Readwise Library address through an SMTP relay.

#### Scenario: Plain markdown converts to EPUB and is emailed

- **WHEN** a caller invokes `save_markdown_as_epub(markdown="# Title\n\nBody.")`
- **AND** all three required env vars (`READWISE_LIBRARY_EMAIL`, `RESEND_API_KEY`, `EPUB_FROM_ADDRESS`) are set
- **THEN** the tool renders the markdown to an EPUB 3 file via pandoc
- **AND** sends an email with the EPUB as an attachment to the configured `READWISE_LIBRARY_EMAIL`
- **AND** returns an `EpubSendResult` with `success=true`, `accepted_at`, `message_id`, `file_size_bytes`, `title`, `recipient`, `location`, `identifier_scheme`, and `note`

#### Scenario: Frontmatter supplies EPUB metadata

- **WHEN** the markdown begins with YAML frontmatter `---\ntitle: T\nauthor: A\ntags: [x, y]\nsummary: S\n---\n`
- **AND** the caller provides no explicit `title`, `author`, `tags`, or `summary`
- **THEN** the EPUB's OPF manifest receives `title=T`, `creator=A`, `subject=[x, y]`, `description=S`
- **AND** the frontmatter block is removed from the rendered EPUB body

#### Scenario: Explicit parameters override frontmatter

- **GIVEN** markdown with frontmatter `title: Frontmatter Title`
- **WHEN** the caller invokes `save_markdown_as_epub(markdown=..., title="Explicit Title")`
- **THEN** the EPUB metadata `title` is `"Explicit Title"`

#### Scenario: Title resolution falls back through frontmatter, H1, then Untitled

- **WHEN** no explicit `title` is provided and no frontmatter is present
- **THEN** the first `# H1` in the markdown body is used as the EPUB title
- **WHEN** neither a title nor an H1 is present
- **THEN** the EPUB title is `"Untitled"`

#### Scenario: Cover image URL is downloaded and embedded

- **WHEN** the caller invokes `save_markdown_as_epub(markdown=..., cover_image_url="https://example.com/cover.jpg")`
- **OR** frontmatter contains `image_url: https://example.com/cover.jpg`
- **THEN** the tool downloads the image to a temporary file
- **AND** passes it to pandoc via `--epub-cover-image=<temp-path>`
- **AND** the resulting EPUB contains the embedded cover image

#### Scenario: Missing cover image URL produces a default pandoc-generated cover

- **WHEN** no `cover_image_url` is provided in parameters or frontmatter
- **THEN** the tool invokes pandoc without `--epub-cover-image`
- **AND** the resulting EPUB has pandoc's default text-only cover with title and author

#### Scenario: Cover image download failure does not block EPUB generation

- **WHEN** a `cover_image_url` is provided but the download fails (timeout, non-200, non-image content-type)
- **THEN** the tool logs the failure
- **AND** proceeds with pandoc generation without a cover image
- **AND** the returned `EpubSendResult` includes `success=true` (the send succeeded; only the cover was lost)

### Requirement: idempotency_key controls EPUB identifier for retry-safe dedup

The tool SHALL accept an optional `idempotency_key` parameter and, when provided, use it as the EPUB `dc:identifier` so retries with the same key collapse into one Library entry.

#### Scenario: idempotency_key becomes the EPUB identifier

- **WHEN** the caller invokes `save_markdown_as_epub(markdown=..., idempotency_key="brief-2026-q2-v1")`
- **THEN** the generated EPUB's OPF manifest contains `dc:identifier` with value `"epub-key-brief-2026-q2-v1"` and scheme `"x-mcp-readwise-idempotency"`
- **AND** `EpubSendResult.identifier_scheme` is `"x-mcp-readwise-idempotency"`

#### Scenario: Two sends with the same idempotency_key produce the same EPUB identifier

- **WHEN** `save_markdown_as_epub(markdown=M, idempotency_key="K")` is invoked twice (same key, same or different markdown)
- **THEN** both generated EPUBs contain the same `dc:identifier` value (`"epub-key-K"`)
- **AND** Readwise's ingest pipeline treats the two emails as updates to the same logical document rather than two separate Library entries

#### Scenario: No idempotency_key falls back to UUID v4

- **WHEN** `save_markdown_as_epub` is invoked without `idempotency_key`
- **THEN** the `dc:identifier` is a fresh UUID v4 with scheme `"uuid"`
- **AND** `EpubSendResult.identifier_scheme` is `"uuid"`
- **AND** two successive sends of identical markdown produce distinct identifiers (and therefore distinct Library entries)

### Requirement: note parameter parity with save_markdown

The tool SHALL accept a `note` parameter aligned with `save_markdown`'s `note` field, surfaced in the EPUB as supplementary metadata.

#### Scenario: note is attached to the EPUB metadata

- **WHEN** the caller invokes `save_markdown_as_epub(markdown=..., note="Context: written for the Q2 planning brief.")`
- **THEN** the value is included in the EPUB's OPF manifest as part of the description (appended after any frontmatter summary) AND optionally rendered as a "Note" preface block at the start of the EPUB body
- **AND** the note is NOT silently dropped under any code path

#### Scenario: Frontmatter note field populates when explicit note is absent

- **WHEN** the markdown frontmatter contains `note: "From the author."`
- **AND** the caller provides no explicit `note` parameter
- **THEN** the resolved note is `"From the author."`

### Requirement: location parameter accepted for parity, surfaced in result

The tool SHALL accept a `location` parameter (matching `save_markdown`'s Literal values) but the email-to-library pipeline always lands documents in the default Library state; the param is echoed back on the result for chaining purposes.

#### Scenario: location echoed on EpubSendResult

- **WHEN** the caller invokes `save_markdown_as_epub(markdown=..., location="later")`
- **THEN** `EpubSendResult.location` is `"later"`
- **AND** the actual EPUB attachment is delivered identically to the library email address regardless of the location value

#### Scenario: location defaults to "new"

- **WHEN** `save_markdown_as_epub` is invoked without `location`
- **THEN** `EpubSendResult.location` is `"new"`

#### Scenario: Docstring documents the informational-only nature

- **WHEN** an LLM client introspects the tool schema
- **THEN** the tool docstring includes text stating that `location` is informational only because the email-to-library pipeline does not route to sub-locations; routing must be done by a follow-up move call after `verify_epub_received` confirms ingest

### Requirement: EPUB output uses the CDIT brand stylesheet tuned for long-form reading

The EPUB output SHALL be styled with a brand-aligned CSS file applying the CDIT visual identity from cdit-works.de, with typography tuned for long-form e-reader reading.

#### Scenario: EPUB CSS uses CDIT brand colors

- **WHEN** the tool generates an EPUB
- **THEN** the embedded stylesheet sets `body` text color to `#272f38` (Carbon)
- **AND** sets `body` background to `#f0eee9` (Cloud Dancer)
- **AND** sets `a` color to `#1f5da0` (Strong Blue)
- **AND** sets `h1` border-bottom color to `#1f5da0` (Strong Blue)
- **AND** sets `blockquote` border-left color to `#5cc6c3` (Mint / Rinsing Rivulet)

#### Scenario: EPUB CSS uses Inter for body AND headings, not League Gothic

- **WHEN** the tool generates an EPUB
- **THEN** the embedded stylesheet sets `body` font-family to `Inter` with sans-serif fallbacks
- **AND** sets `h1`, `h2`, `h3` font-family ALSO to `Inter` (NOT `League Gothic`), with sans-serif fallbacks — chapter headings rely on Inter weight 800 with tight tracking, never on a condensed display face
- **AND** sets `code` / `pre` font-family to `JetBrains Mono` with monospace fallbacks
- **AND** applies tracking `-0.02em` and line-height `1.15` to headings (book-context air, not website-condensed)

#### Scenario: Body styling is tuned for long-form reading

- **WHEN** the tool generates an EPUB
- **THEN** the embedded stylesheet sets `body` line-height to `1.7` (book-context, not screen-default `1.65`)
- **AND** sets `body` text-align to `left` (never `justify`; readers' justification renderers mangle hyphenation)
- **AND** enables `hyphens: auto` for better paragraph rag

#### Scenario: CSS file is shipped as a static asset, not generated per-call

- **WHEN** the tool is deployed (Docker image or local install)
- **THEN** the CSS file is present at `mcp_readwise/assets/epub/cdit-style.css`
- **AND** the file is included in the package metadata so it ships with the wheel
- **AND** the file is bundled into the Docker image

#### Scenario: Inter is embedded as static woff2 subsets, not variable

- **WHEN** the tool is deployed
- **THEN** the assets directory contains Inter weight 400, 700, and 800 as static woff2 files (latin + latin-ext subsets)
- **AND** the assets directory does NOT contain Inter Variable woff2 (variable-axis files)
- **AND** the EPUB references these static files via `@font-face` rules
- **AND** total embedded font payload is approximately 110–140 KB (latin + latin-ext, three weights)

#### Scenario: League Gothic and JetBrains Mono are not embedded in the EPUB body

- **WHEN** the tool generates an EPUB
- **THEN** the EPUB does NOT contain League Gothic font files in its body assets (any League Gothic asset is reserved for the cover plate only)
- **AND** the EPUB does NOT contain JetBrains Mono font files (system mono fallback is used)

### Requirement: Email delivery uses SMTP through Resend (or configured SMTP host)

The tool SHALL deliver the EPUB by sending an email via `aiosmtplib` to the configured SMTP host using STARTTLS.

#### Scenario: SMTP send to Resend default host

- **GIVEN** `SMTP_HOST="smtp.resend.com"`, `SMTP_PORT=587`, `RESEND_API_KEY="re_…"`, `EPUB_FROM_ADDRESS="mcp-readwise@cdit-dev.de"`, `READWISE_LIBRARY_EMAIL="custom@library.readwise.io"`
- **WHEN** `save_markdown_as_epub` runs
- **THEN** the tool connects to `smtp.resend.com:587` with STARTTLS
- **AND** authenticates with username `"resend"` and password equal to `RESEND_API_KEY`
- **AND** sends a message with `From: mcp-readwise@cdit-dev.de`, `To: custom@library.readwise.io`, `Subject: <resolved title>`
- **AND** attaches the EPUB as a base64-encoded MIME part with `Content-Type: application/epub+zip` and `Content-Disposition: attachment; filename="<safe-filename>.epub"`

#### Scenario: SMTP host override works for alternate providers

- **GIVEN** `SMTP_HOST="smtp.postmarkapp.com"` and `SMTP_PORT=587`
- **WHEN** `save_markdown_as_epub` runs
- **THEN** the tool connects to the overridden host instead of Resend
- **AND** uses the provided `RESEND_API_KEY` value as the SMTP password (the env var name is retained for config consistency; semantically it's "SMTP password")

#### Scenario: One retry on transient SMTP failure

- **WHEN** the first SMTP attempt raises `aiosmtplib.SMTPException` with a transient error code (4xx)
- **THEN** the tool waits with exponential backoff (1s, then 4s)
- **AND** retries up to one additional time
- **AND** if all retries fail, raises `SmtpDeliveryError` with the final server response code

#### Scenario: Authentication failure surfaces immediately without retry

- **WHEN** the SMTP server rejects authentication (5xx code, typically 535)
- **THEN** the tool does NOT retry
- **AND** raises `SmtpDeliveryError` with the auth-failure response

### Requirement: EpubSendResult returns the full recipient and chains into verify_epub_received

The tool SHALL return an `EpubSendResult` whose `title` and `accepted_at` fields are directly chainable into `verify_epub_received`. The `recipient` field SHALL contain the full email address used (not masked).

#### Scenario: Recipient is returned in full

- **WHEN** the tool sends successfully to `caseyromkes-personal@library.readwise.io`
- **THEN** `EpubSendResult.recipient` equals `"caseyromkes-personal@library.readwise.io"` exactly
- **AND** the full address is the value that ends up in caller-visible transcripts

#### Scenario: Result fields chain into verify_epub_received

- **WHEN** `save_markdown_as_epub` returns `EpubSendResult(title=T, accepted_at=S, ...)`
- **THEN** invoking `verify_epub_received(title=T, since=S)` is a syntactically valid call with the right semantics
- **AND** no field-name translation is required between the two tools

#### Scenario: Result includes async-contract notice

- **WHEN** the tool returns `EpubSendResult`
- **THEN** the `note` field leads with a string indicating the document will appear asynchronously (e.g., "Sent. Document appears in Readwise Reader within 1–5 minutes. Use verify_epub_received to confirm.")

#### Scenario: Result includes message ID and file size

- **WHEN** the SMTP server accepts the message
- **THEN** the `EpubSendResult.message_id` is populated from the server response (or a locally-generated UUID if the server does not return one)
- **AND** the `EpubSendResult.file_size_bytes` is the actual byte length of the EPUB attached

### Requirement: Tool docstring leads with async contract and configuration requirements

The MCP-facing docstring of `save_markdown_as_epub` SHALL lead with the asynchronous nature of the operation and the required environment variables, so an LLM agent reading the schema before invocation has the information needed to set human expectations correctly.

#### Scenario: Docstring leads with ASYNC notice

- **WHEN** an LLM client introspects the tool's metadata
- **THEN** the first line of the description contains the literal text "ASYNC" (uppercase) and references that the document appears in 1–5 minutes
- **AND** explicitly directs the agent not to tell the human the document is available until `verify_epub_received` confirms it

#### Scenario: Docstring lists required env vars by name

- **WHEN** an LLM client introspects the tool's metadata
- **THEN** the description names the three required env vars: `READWISE_LIBRARY_EMAIL`, `RESEND_API_KEY`, `EPUB_FROM_ADDRESS`
- **AND** notes that missing configuration raises `ConfigurationError` immediately

### Requirement: Configuration is lazily validated and secrets are never logged or returned

Required env vars SHALL be validated at first invocation of the tool, not at server startup. Secret values SHALL never appear in logs, error messages, or `/health` output.

#### Scenario: Tool refuses to run when configuration is incomplete

- **GIVEN** `RESEND_API_KEY` is unset
- **WHEN** `save_markdown_as_epub` is invoked
- **THEN** the tool raises `ConfigurationError` with a message naming the missing env var(s)
- **AND** the error does NOT include the value of any set secret

#### Scenario: Server starts successfully with epub-sender config absent

- **GIVEN** none of `READWISE_LIBRARY_EMAIL`, `RESEND_API_KEY`, `EPUB_FROM_ADDRESS` are set
- **WHEN** the MCP server starts
- **THEN** the server starts successfully
- **AND** all other tools (12 of them) remain registered and functional
- **AND** `/health` reports `epub_sender.configured=false`

#### Scenario: Health endpoint exposes configured flag but not secrets or library email

- **WHEN** the configuration is complete and `/health` is queried
- **THEN** the response contains an `epub_sender` object with `configured=true`, `smtp_host`, `smtp_port`, `from_address`
- **AND** the response does NOT contain `READWISE_LIBRARY_EMAIL` in plaintext (only `library_email_set` as a boolean)
- **AND** the response does NOT contain the `RESEND_API_KEY` value or the SMTP password
- **AND** the `from_address` value MAY appear in plaintext because it is the public-facing sender address visible in any sent mail

### Requirement: EPUB file size is bounded

The tool SHALL refuse to send an EPUB larger than 20 MiB. The binding constraint is Readwise's 30 MB total email size cap on the email-to-library pipeline; base64 encoding inflates binary attachments by ~33% so 20 MiB raw fits within 30 MB encoded with margin for MIME overhead.

#### Scenario: Oversize EPUB is rejected before send

- **WHEN** the generated EPUB exceeds 20 MiB (20,971,520 bytes)
- **THEN** the tool does NOT attempt the SMTP send
- **AND** raises `EpubTooLargeError` with the actual size in the message

### Requirement: verify_epub_received companion tool confirms ingest by querying Reader

The MCP server SHALL expose a `verify_epub_received` tool that queries the Reader document list to confirm whether a recently-sent EPUB has landed in the Library.

#### Scenario: Confirmation of a landed EPUB

- **GIVEN** `save_markdown_as_epub` was invoked and returned `EpubSendResult(title="My Brief", accepted_at="2026-05-11T10:00:00Z", ...)`
- **AND** Readwise has ingested the corresponding document
- **WHEN** the caller invokes `verify_epub_received(title="My Brief", since="2026-05-11T10:00:00Z")`
- **THEN** the tool queries Reader for documents with `category="epub"` updated after the `since` timestamp
- **AND** finds a document whose title matches (case-insensitive contains)
- **AND** returns `VerifyResult(found=true, document=ReaderDocument(...), note="Found in Reader Library.")`

#### Scenario: Not-yet-ingested EPUB reported as such with retry guidance

- **GIVEN** a recently-sent EPUB has not yet been ingested by Readwise
- **WHEN** `verify_epub_received(title=..., since=...)` is invoked less than 60 seconds after the send
- **THEN** the result is `VerifyResult(found=false, document=null, note="Too early — Readwise typically ingests within 1–5 minutes. Retry shortly.")`
- **WHEN** invoked between 60 seconds and 5 minutes after the send
- **THEN** the note is `"Not yet — ingest pending. Retry in 1–2 minutes."`
- **WHEN** invoked between 5 and 15 minutes after the send and still not found
- **THEN** the note is `"Late — Readwise ingest usually completes by 5 min. May have failed."`
- **WHEN** invoked more than 15 minutes after the send and still not found
- **THEN** the note is `"Not found — check SMTP delivery (Resend dashboard) and library email."`

#### Scenario: Fuzzy title matching is enabled by default

- **GIVEN** a document with title `"My Brief - Q2 2026"` exists in Reader
- **WHEN** the caller invokes `verify_epub_received(title="My Brief", since=...)`
- **THEN** the match succeeds (case-insensitive contains)
- **WHEN** the caller invokes `verify_epub_received(title="My Brief", since=..., fuzzy=False)`
- **THEN** the match requires exact title equality (case-insensitive) and would not match in this case

#### Scenario: verify_epub_received does not require epub_sender configuration

- **GIVEN** none of the EPUB-sender env vars are set
- **WHEN** `verify_epub_received` is invoked
- **THEN** the tool runs successfully (it depends only on `READWISE_TOKEN`, which the other 11 read/write tools already require)
- **AND** queries Reader documents as expected

### Requirement: Tools are registered alongside save_url and save_markdown

The `save_markdown_as_epub` and `verify_epub_received` tools SHALL be registered on the FastMCP server, and `/health` SHALL report the updated tool count.

#### Scenario: Health endpoint reports 14 tools

- **WHEN** a GET is issued to `/health` after registration
- **THEN** the response JSON includes `"tools": 14`

#### Scenario: Both tools are callable via MCP

- **WHEN** the MCP client lists available tools
- **THEN** `save_markdown_as_epub` appears with its docstring as description and the declared parameter schema (`markdown`, `title`, `author`, `summary`, `tags`, `note`, `cover_image_url`, `published_date`, `location`, `idempotency_key`)
- **AND** `verify_epub_received` appears with its docstring as description and the declared parameter schema (`title`, `since`, `fuzzy`)
