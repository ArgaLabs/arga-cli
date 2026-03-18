# Arga CLI

`arga` is the command-line interface for authenticating with Arga, installing MCP configuration into supported coding agents, and starting validation runs against deployed apps or pull requests.

## What It Does

- Authenticates your machine with Arga using the device login flow.
- Stores a device-scoped API key locally so each terminal/device can be revoked independently.
- Shows the currently authenticated user and workspace.
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

Remove the saved device credential:

```bash
arga logout
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

`arga validate url` is also available and currently behaves the same as `arga test url`:

```bash
arga validate url --url https://demo-app.com --prompt "test checkout"
```

## Command Reference

### Authentication

```bash
arga login
arga whoami
arga logout
```

- `arga login` opens the browser to complete Arga's device authorization flow.
- `arga whoami` verifies the saved API key and prints the GitHub login plus workspace.
- `arga logout` removes the local credential and attempts to revoke the current device on the server.

### Validation

```bash
arga test url --url https://demo-app.com --prompt "test login flow"
arga validate url --url https://demo-app.com --prompt "test checkout"
arga validate pr --repo arga-labs/validation-server --pr 182
```

- `arga test url` starts a one-off validation against a deployed URL.
- `arga validate url` is an equivalent URL-validation entry point under the `validate` namespace.
- `arga validate pr` starts GitHub-backed PR validation for a repository and pull request number.

For URL validation, you can optionally provide credentials:

```bash
arga test url \
  --url https://demo-app.com \
  --prompt "log in and create an order" \
  --email test@company.com \
  --password supersecret
```

Both `--email` and `--password` must be supplied together.

## Supported MCP Targets

`arga mcp install` writes or updates MCP configuration for supported agents when they are detected locally:

- `~/.cursor/mcp.json`
- `~/.claude/mcp.json`
- `~/.config/codex/mcp.json`

The installed server is named `arga-context` and points to:

```text
<api-url>/mcp
```

using an `Authorization: Bearer <api_key>` header generated from your saved CLI login.

## MCP Installation

Install or update MCP config after you have logged in:

```bash
arga login
arga mcp install
```

The installer:

- Detects supported local agent config directories.
- Preserves existing `mcpServers` entries.
- Merges in the generated `arga-context` server definition.
- Returns a non-zero exit code if no supported targets are detected or if any target cannot be updated.

If you need to add the server manually, the generated config looks like:

```json
{
  "mcpServers": {
    "arga-context": {
      "url": "https://api.argalabs.com/mcp",
      "headers": {
        "Authorization": "Bearer <your-api-key>"
      }
    }
  }
}
```

## Using A Custom API URL

By default, the CLI targets `https://api.argalabs.com`.

To point it at another environment, pass `--api-url` or set `ARGA_API_URL`:

```bash
arga login --api-url http://localhost:8000
arga mcp install --api-url http://localhost:8000
arga test url --api-url http://localhost:8000 --url https://demo-app.com --prompt "test checkout"
arga validate url --api-url http://localhost:8000 --url https://demo-app.com --prompt "test checkout"
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

That file contains the saved API key plus device metadata returned during `arga login`.
