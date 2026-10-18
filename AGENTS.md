# Repository scope

Before any change, read `docs/development-delivery.md`; create/sync the task branch first. Every feature/fix needs relevant live read-only acceptance, updated evidence and a draft PR attached to the chat. Use `.github/PULL_REQUEST_TEMPLATE.md`, handle reviews with `docs/review.md`, and do not merge before the user's explicit request.

This package is a read-only Xiaohongshu Python library and CLI. Target Python 3.14 (standard GIL build), uv, hatchling, src layout. Keep the installed package independent of local Codex paths, sibling repositories, Node, Go and model providers.

## Boundaries

- `browser.py`: Chrome process/profile ownership and sequential local CDP.
- `scripts.py`: read-only page probes and bounded navigation controls.
- `client.py`: site flow, lifecycle, limits and stable JSON envelopes.
- `models.py`: normalization and public redaction.
- `cli.py`: parameters, private local token cache and JSON serialization.
- Other tools and the travel planner may import this package; never import the planner back.

Use officially supported interfaces when they satisfy a requirement. This package covers the current lack of a suitable consumer note-research interface; it is not official. Prefer verified page state and page context operations over brittle reimplementations of signing. Do not claim CDP is faster without comparable measurements.

No posting, liking, following, comments, account edits, CAPTCHA bypass or generic request proxy. Manual login is expected. Preserve existing local profiles and cookies. Never commit, package, print or copy real credentials, profile data, signed URLs or private runtime caches. Fixture credentials must be clearly synthetic. Public CLI output must omit access tokens.

## Quality loop

Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, then build a wheel and run the directory-external installed-wheel smoke. Add behavioral checks for parsing, redaction, ownership, bounds and error handling. Network/browser acceptance is opt-in and must report what was actually read, including comment scope. Release notes must distinguish tested Windows behavior from merely implemented cross-platform branches.

Update README/API documentation together with contract changes. Keep JSON schemaVersion=1 backward compatible within 0.1.x. The library and CLI must install and work alone; sharing an integrating application's environment is optional. Business adaptation belongs in the consumer. No runtime dependency on other repository source paths.
