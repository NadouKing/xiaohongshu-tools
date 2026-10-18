# Deployment

Use CPython 3.14, uv and system Google Chrome. From this repository run `uv sync --locked`, followed by `uv run xhs login`. Scan the site's normal QR code in the visible dedicated window. Future headless queries reuse the profile.

Default Windows storage is `%LOCALAPPDATA%/xiaohongshu-tools/`; Linux uses `$XDG_STATE_HOME` or `~/.local/state`; macOS currently uses the same state fallback. `XHS_PROFILE_DIR` or `--profile-dir` overrides the profile. `XHS_CHROME_PATH` or `--chrome-path` overrides executable discovery. Do not point either at another platform's profile or your daily Chrome profile.

`--cookies-file` explicitly imports a local JSON array or v2 envelope into the dedicated new Chrome. The file is never rewritten or automatically discovered. Cookie scope is limited to Xiaohongshu. Expired cookies are skipped. Importing valid cookies is not proof of authentication; verify `xhs session`.

`xhs search` caches detail access parameters in profile-adjacent `private/search-tokens.json` for at most 12 hours; stdout contains no token. Run `xhs detail NOTE_ID` after search using the same profile. There is deliberately no token CLI flag, so parameters need not be put into shell history.

Typical failures:

| Code | Action |
|---|---|
| `chrome_not_found` | Install Chrome or provide its executable path. |
| `profile_busy` | Finish the other command using that profile, then retry. |
| `browser_start_failed` | Check executable and external Chrome profile ownership. |
| `authentication_required` | Run `xhs login`; do not delete existing login data. |
| `session_unknown` | No confirmed login/logout UI was observed; check network or site adaptation. |
| `verification_required` | Use visible Chrome and complete the site's normal human verification. |
| `page_data_unavailable` | Confirm login and note availability; selectors/state may need updating. |
| `sort_refresh_timeout` | Retry; stale results are not returned under a false sort label. |

No service needs to run permanently. The library and CLI both work with this repository's environment alone. A consuming application may instead install this package into its own environment and import it directly; it owns business adaptation. The Chrome binary and local login profile are external prerequisites, not bundled runtime dependencies.
