# Environment and installed artifact checks

Runtime: CPython >=3.14, standard GIL build; websockets >=15,<18; installed Chrome. Python patch updates should be kept current by the integrating application. `.python-version` selects the 3.14 family rather than freezing a security patch. `uv.lock` records independent development dependencies. The main travel app owns its own locked environment for all three packages.

Initial acceptance used Python 3.14.8, websockets 17.2 and Windows Chrome. No claim of Linux/macOS live acceptance is made.

Local checks are offline: parsing, redaction, cookie scope and non-modification, exclusive profile ownership, sample bounds, typed auth/verification failures, private-cache expiry and CLI failure output.

Build `uv build`, then use `scripts/smoke_installed_wheel.py WHEEL`. It creates a temporary virtual environment, installs the wheel and declared dependencies, removes PYTHONPATH and checks import/CLI outside the source directory. The temporary environment is a packaging test; no per-tool production environment is created.

The opt-in live script uses a logged-in dedicated Chrome and a low fixed volume: one search and up to five candidate details until two successful results. It emits sanitized counts/timings/public note identity only. Do not save raw state or debug WebSocket messages in a public artifact.
