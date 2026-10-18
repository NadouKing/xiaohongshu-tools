# Architecture

`CLI → client → browser CDP → local Chrome → Xiaohongshu web application`.
The library is the primary integration boundary. The CLI is an independent interface to the same client, not a subprocess dependency for the main planner.

## Browser and state

The client lazily launches a dedicated Chrome, with a loopback-only random CDP port and a non-default user-data-dir. OS file locking prevents concurrent owners and releases on process death. Chrome remains alive inside an async context, so search followed by several details reuses one process and login. Each operation closes its own page; close shuts down only the child process this client started.

The existing site's browser application performs signed network requests itself. The tool reads hydrated search/note state through `Runtime.evaluate`; if comment state is unavailable, it reads comment DOM text. A bounded scroll loop requests more through the site's own lazy loading. This avoids implementing volatile signing. It does not guarantee that plain HTTP would be unavailable or slower; neither an HTTP signature implementation nor comparative benchmark is claimed.

The page JavaScript is embedded Python string data included in the wheel and executed by Chrome. Node is not required. No HTML parsing library is required. Page state and DOM selectors remain subject to site changes, which surface as typed errors.

## Contracts

Async public methods return schemaVersion=1 envelopes. The source is `xiaohongshu`, timestamps are UTC ISO 8601, and elapsedMs covers the operation after client startup when using an explicit context. Constructor supports explicit cookie import into the new profile; only the source cookie file is read.

Access tokens from search are ephemeral library results or CLI-private cache entries. Public URLs are canonical note URLs; CLI serialization removes tokens and query strings recursively. The main application must apply equivalent filtering before saving library results.

Search is a first-page sample of up to 20 notes. Comment retrieval is a maximum of 100 primary comments, with a 12-second loading budget and stagnation stop. Replies are not expanded. `commentsHasMore` describes additional primary-comment sampling where observable, not complete coverage. `commentScope` remains `bounded_top_level_sample` even if the page reports its end.

## Extension order

First maintain reliable search/detail/comments and errors. Then benchmark representative cold/warm calls before pursuing page-function or HTTP shortcuts. Add any new official interface as a separately verified path. Video transcription, full pagination, publishing and a remote MCP service are outside v0.1.
