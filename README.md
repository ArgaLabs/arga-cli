# Arga CLI

`arga` is the command-line interface for authenticating with Arga, installing MCP configuration into supported coding agents, and starting browser-based validation runs against deployed apps.

## What It Does

- Authenticates your machine with Arga using the device login flow.
- Installs MCP configuration into supported local agents.
- Starts URL validation runs from the terminal.
- Starts pull request validation runs from the terminal.

## Installation

Once published to PyPI:

```bash
uv tool install arga-cli
```

You can also install it with `pipx` or `pip`:

```bash
pipx install arga-cli
pip install arga-cli
```

After installation, the executable is:

```bash
arga --help
```

## Quick Start

Authenticate:

```bash
arga login
arga whoami
```

Install MCP configuration for detected agents:

```bash
arga mcp install
```

Start a browser validation run:

```bash
arga test url --url https://demo-app.com --prompt "test the login flow"
```

Start a pull request validation run:

```bash
arga validate pr --repo arga-labs/validation-server --pr 182
```

## Supported MCP Targets

`arga mcp install` writes or updates MCP configuration for supported agents when they are detected locally:

- `~/.cursor/mcp.json`
- `~/.claude/mcp.json`
- `~/.config/codex/mcp.json`

## Using A Custom API URL

By default, the CLI targets `https://api.argalabs.com`.

To point it at another environment, pass `--api-url` or set `ARGA_API_URL`:

```bash
arga login --api-url http://localhost:8000
arga mcp install --api-url http://localhost:8000
arga test url --api-url http://localhost:8000 --url https://demo-app.com --prompt "test checkout"
arga validate pr --api-url http://localhost:8000 --repo arga-labs/validation-server --pr 182
```

```bash
export ARGA_API_URL=http://localhost:8000
arga login
```

## Local Development

```bash
uv sync
uv run pytest
uv run arga --help
```

To install the current checkout as a shell command:

```bash
uv tool install -e .
```

## Config Storage

The CLI stores its local auth state in:

```bash
~/.config/arga/config.json
```
