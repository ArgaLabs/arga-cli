# AGENTS.md

## Cursor Cloud specific instructions

This is a Python CLI project (`arga-cli`) managed with **uv**. The `uv.lock` lockfile pins all dependencies.

### Quick reference

| Task | Command |
|------|---------|
| Install deps | `uv sync` |
| Lint | `uv run ruff check .` |
| Format check | `uv run ruff format --check .` |
| Tests | `uv run pytest` |
| Run CLI | `uv run arga --help` |

See `README.md` "Local Development" section for full details.

### Notes

- All tests are fully mocked (no live API or network access needed). `uv run pytest` is self-contained.
- Commands that hit the Arga API (`login`, `whoami`, `test url`, `mcp install`) require authentication via `arga login`, which needs network access to `api.argalabs.com` (or a local API at `localhost:8000` via `--api-url`). Without auth, these commands exit with a clear "Not authenticated" error — this is expected behavior, not a broken environment.
- The `ARGA_API_URL` env var overrides the default API endpoint (`https://api.argalabs.com`).
- Python 3.12+ is required (`pyproject.toml` specifies `>=3.12`).
- `uv` must be on `PATH`. It is installed to `~/.local/bin` by the official installer.
