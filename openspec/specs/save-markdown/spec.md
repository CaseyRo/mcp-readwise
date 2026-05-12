## ADDED Requirements

### Requirement: save_markdown tool accepts markdown content and pushes it to Readwise Reader

The MCP server SHALL expose a `save_markdown` tool that converts a markdown string into a Readwise Reader document via the `/api/v3/save/` endpoint.

#### Scenario: Plain markdown with explicit title

- **WHEN** a caller invokes `save_markdown(markdown="# Hello\n\nWorld.", title="Greeting")`
- **THEN** the tool renders the markdown to HTML
- **AND** POSTs to `/api/v3/save/` with `html=<rendered>`, `title="Greeting"`, `category="epub"`, `should_clean_html=false`, and a synthetic `url`
- **AND** returns a `ReaderDocument` populated from the API response

#### Scenario: Markdown with YAML frontmatter supplies title and tags

- **WHEN** the markdown begins with `---\ntitle: My Note\nauthor: Casey\ntags: [research, draft]\n---\n# Body\n\nContent.`
- **AND** the caller invokes `save_markdown(markdown=...)` without explicit `title`, `author`, or `tags`
- **THEN** the tool extracts `title="My Note"`, `author="Casey"`, `tags=["research", "draft"]` from frontmatter
- **AND** strips the frontmatter block from the rendered HTML
- **AND** POSTs to Readwise with the resolved metadata

#### Scenario: Title resolution prefers explicit param over frontmatter over H1

- **GIVEN** markdown with frontmatter `title: From Frontmatter` and body `# From H1`
- **WHEN** the caller invokes `save_markdown(markdown=..., title="Explicit")`
- **THEN** the resolved title is `"Explicit"`
- **WHEN** the caller invokes `save_markdown(markdown=...)` (no explicit title)
- **THEN** the resolved title is `"From Frontmatter"`
- **WHEN** the frontmatter is removed and no `title=` is passed
- **THEN** the resolved title is `"From H1"`
- **WHEN** none of the above are present
- **THEN** the resolved title is `"Untitled"`

#### Scenario: Synthetic URL is stable across re-uploads of identical content

- **GIVEN** markdown content `M` and title `T`
- **WHEN** `save_markdown` is invoked twice in succession with `(M, T)`
- **THEN** both calls produce the same `source_url` value of form `https://mcp-readwise.local/md/<16hex>`
- **AND** the SHA1 hash is computed over `T + M[:512]`

#### Scenario: Category defaults to "epub" but caller can override

- **WHEN** `save_markdown(markdown=...)` is invoked without explicit `category`
- **THEN** the request to Readwise includes `category="epub"`
- **WHEN** the caller passes `category="article"`
- **THEN** the request includes `category="article"`
- **AND** the accepted values are exactly the Reader API set: `article`, `email`, `rss`, `highlight`, `note`, `pdf`, `epub`, `tweet`, `video`

#### Scenario: Location defaults to "new" but caller can override

- **WHEN** `save_markdown(markdown=...)` is invoked without explicit `location`
- **THEN** the request to Readwise includes `location="new"`
- **WHEN** the caller passes `location="later"`
- **THEN** the request includes `location="later"`
- **AND** the accepted values are `new`, `later`, `shortlist`, `archive` (matching `save_url`)

#### Scenario: should_clean_html is always false

- **WHEN** any `save_markdown` invocation is made
- **THEN** the request to Readwise includes `should_clean_html=false`
- **AND** the rendered HTML is sent unmodified to Readwise

#### Scenario: Tool returns the Reader document with synthetic URL preserved

- **WHEN** `save_markdown` completes successfully
- **THEN** the returned `ReaderDocument` has `source_url` matching the synthetic URL sent to Readwise
- **AND** has the `id`, `title`, `location`, `category`, `tags`, and timestamp fields populated from the API response

#### Scenario: Malformed frontmatter falls back to treating content as body

- **GIVEN** markdown beginning with `---` but missing the closing fence
- **OR** markdown with `---` followed by content that does not parse as `key: value` pairs
- **WHEN** `save_markdown` is invoked
- **THEN** the tool treats the entire markdown as body (no frontmatter extracted)
- **AND** falls back through the title resolution chain (H1 or "Untitled")
- **AND** does not raise an error

### Requirement: Markdown rendering supports common extensions

The render pipeline SHALL use the Python `markdown` library with extensions enabling tables, footnotes, fenced code blocks, attribute lists, definition lists, smart quotes, and sane lists.

#### Scenario: Tables render to HTML table elements

- **WHEN** the markdown contains a pipe-table
- **THEN** the rendered HTML contains `<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>` elements

#### Scenario: Footnotes render with linked references

- **WHEN** the markdown contains `[^1]` references and `[^1]: footnote text` definitions
- **THEN** the rendered HTML contains a footnote section with anchor links

#### Scenario: Fenced code blocks preserve language hints

- **WHEN** the markdown contains ` ```python ` fenced blocks
- **THEN** the rendered HTML contains `<pre><code class="language-python">` (or equivalent class)

### Requirement: Tool is registered alongside save_url and increments tool count

The `save_markdown` tool SHALL be registered on the FastMCP server next to `save_url` and the `/health` endpoint SHALL report the updated tool count.

#### Scenario: Health endpoint reports 12 tools

- **WHEN** a GET is issued to `/health` after registration
- **THEN** the response JSON includes `"tools": 12`

#### Scenario: Tool is callable via MCP

- **WHEN** the MCP client lists available tools
- **THEN** `save_markdown` appears in the list with its docstring as description and the declared parameter schema
