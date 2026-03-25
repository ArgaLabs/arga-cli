# Arga CLI

`arga` is the command-line interface for authenticating with Arga, installing MCP configuration into supported coding agents, and starting validation runs against deployed apps or pull requests.

## What It Does

- Authenticates your machine with Arga using the device login flow.
- Stores a device-scoped API key locally so each terminal/device can be revoked independently.
- Shows the currently authenticated user and workspace.
- Installs MCP configuration into supported local agents.
- Starts URL validation runs from the terminal.
- Starts pull request validation runs from the terminal.
- Wraps `git commit` and `git push` with Arga skip-validation helpers.
- Starts and inspects Arga app scans.

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

Create a commit that skips Arga validation:

```bash
arga commit -m "docs: update examples" --skip
arga push --skip
```

Inspect or update automatic validation settings:

```bash
arga validate install arga-labs/validation-server
arga validate config arga-labs/validation-server
arga validate config set arga-labs/validation-server --trigger branch --branch main --comments on
```

Start an app scan and inspect it later:

```bash
arga scan https://demo-app.com --budget 200
arga scan status <run_id>
arga scan report <run_id>
```

List and inspect recent validation runs:

```bash
arga runs list --repo arga-labs/validation-server --limit 20
arga runs status <run_id>
arga runs cancel <run_id>
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
arga validate install arga-labs/validation-server
arga validate config arga-labs/validation-server
arga validate config set arga-labs/validation-server --trigger branch --branch main --comments on
```

- `arga test url` starts a one-off validation against a deployed URL.
- `arga validate url` is an equivalent URL-validation entry point under the `validate` namespace.
- `arga validate pr` starts GitHub-backed PR validation for a repository and pull request number.
- `arga validate install <repo>` installs the GitHub webhook for automatic validation on a repository.
- `arga validate config <repo>` shows the current automatic validation settings, including install state, trigger mode, selected branch, and PR comment behavior.
- `arga validate config set <repo>` updates the automatic validation settings. Any omitted options keep their current value.

For URL validation, you can optionally provide credentials:

```bash
arga test url \
  --url https://demo-app.com \
  --prompt "log in and create an order" \
  --email test@company.com \
  --password supersecret
```

Both `--email` and `--password` must be supplied together.

### App Scans

```bash
arga scan https://demo-app.com --budget 200
arga scan status <run_id>
arga scan report <run_id>
```

- `arga scan <url>` starts an app scan, waits for the generated scan plan to be ready, and auto-approves it so execution can begin.
- `--budget` controls the red-team action budget and defaults to `200`.
- `arga scan status <run_id>` prints the current run status and anomaly count.
- `arga scan report <run_id>` prints the final JSON report once the scan has completed.

### Validation Runs

```bash
arga runs list --repo arga-labs/validation-server --status running --limit 20
arga runs status <run_id>
arga runs cancel <run_id>
```

- `arga runs list` shows recent PR and branch validation runs in table form.
- `--repo` narrows the list to a single repository.
- `--status` accepts `completed`, `failed`, or `running`. The `running` filter includes non-terminal states such as `queued`.
- `arga runs status <run_id>` prints a detailed summary for a specific run.
- `arga runs cancel <run_id>` cancels the run through the validation API.

### Git Wrappers

```bash
arga commit -m "docs: update examples" --skip
arga push --skip
```

- `arga commit` delegates to `git commit`.
- `arga commit --skip` appends a final `[skip arga]` paragraph to the commit message so Arga skips validation for that head commit.
- `arga push` delegates to `git push`.
- `arga push --skip` verifies the current `HEAD` commit already contains `[skip arga]` before pushing. This is safest when the commit was created with `arga commit --skip`.

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
