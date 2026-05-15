# Arga CLI

`arga` is the command-line interface for authenticating with Arga, installing MCP configuration into supported coding agents, and managing Arga previews, scenarios, saved browser tests, and live test runs.

## What It Does

- Authenticates your machine with Arga using the device login flow.
- Stores a device-scoped API key locally so each terminal/device can be revoked independently.
- Shows the currently authenticated user and workspace.
- Installs MCP configuration into supported local agents.
- Starts preview runs for URLs, PR checks, sandboxes, and twins.
- Manages test-runner scenarios, saved tests, blocks, and run history.
- Imports, exports, validates, and summarizes agent-editable TestConfig JSON.
- Wraps `git commit` and `git push` with Arga skip-validation helpers.

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

Start a browser URL run:

```bash
arga test-runner runs url --url https://demo-app.com --prompt "test the login flow"
```

Start a PR check preview:

```bash
arga previews pr-checks run --repo arga-labs/validation-server --pr 182
```

Run a sandbox preview for a branch:

```bash
arga previews sandboxes run --repo arga-labs/app --branch feature/demo --twins slack,jira,linear
arga previews sandboxes status <sandbox_id>
arga previews sandboxes logs <sandbox_id>
arga previews sandboxes teardown <sandbox_id>
```

Provision twins directly:

```bash
arga previews twins list
arga previews twins provision --twins gitlab,linear --ttl 60 --wait
arga previews twins status <run_id>
arga previews twins extend <run_id> --ttl 90
arga previews twins lock <run_id>
arga previews twins teardown <run_id>
```

Create and run saved tests:

```bash
arga test-runner tests create --name "Checkout" --run-id <demo_run_id> --repo arga-labs/app --ci
arga test-runner tests run <test_id> --url https://preview.example.com
```

Any of these commands accept `--json` for machine-parseable output:

```bash
arga test-runner runs url --url https://demo-app.com --prompt "test login" --json
arga test-runner tests list --json
arga test-runner runs get <run_id> --json
```

Create a commit that skips Arga validation:

```bash
arga commit -m "docs: update examples" --skip
arga push --skip
```

Inspect or update automatic validation settings:

```bash
arga previews pr-checks install arga-labs/validation-server
arga previews pr-checks config arga-labs/validation-server
arga previews pr-checks config-set arga-labs/validation-server --trigger branch --branch main --comments on
arga previews pr-checks enabled
arga previews pr-checks disable arga-labs/validation-server --trigger branch
```

List and inspect recent validation runs:

```bash
arga runs list --repo arga-labs/validation-server --limit 20
arga runs status <run_id>
arga runs logs <run_id>
arga runs cancel <run_id>
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

### Previews

```bash
arga previews sandboxes run --repo arga-labs/app --branch feature/demo
arga previews sandboxes status <sandbox_id>
arga previews sandboxes logs <sandbox_id>
arga previews sandboxes teardown <sandbox_id>
arga previews pr-checks run --repo arga-labs/validation-server --pr 182
arga previews twins list
arga previews twins provision --twins slack,jira,linear,gitlab --ttl 60 --wait
arga previews twins status <run_id>
arga previews twins extend <run_id> --ttl 90
arga previews twins lock <run_id>
arga previews twins teardown <run_id>
arga previews pr-checks install arga-labs/validation-server
arga previews pr-checks config arga-labs/validation-server
arga previews pr-checks config-set arga-labs/validation-server --trigger branch --branch main --comments on
arga previews pr-checks enabled
arga previews pr-checks enable arga-labs/validation-server --trigger branch
arga previews pr-checks disable arga-labs/validation-server --trigger branch
```

- `arga previews sandboxes run` starts a branch-backed or PR-backed sandbox preview. Use `--twins`, `--scenario-id`, `--ttl`, and repeated `--env KEY=VALUE` entries to shape the environment.
- `arga previews sandboxes status/logs/teardown` inspect readiness, stream lifecycle events, or end a sandbox preview.
- `arga previews pr-checks run` starts GitHub-backed PR validation for a repository and pull request number, PR URL, or branch.
- `arga previews twins list` shows the supported twin catalog from `validation-server`.
- `arga previews twins provision` provisions twins without running a browser test. Use `--scenario-id` or `--scenario-prompt` to seed them, and `--private` to keep them behind proxy auth.
- `arga previews twins extend` / `lock` / `teardown` adjust TTL, disable public access, or end the quickstart session.
- `arga previews pr-checks install/config/config-set/enabled/enable/disable` manage automatic PR check settings.

`arga validate pr` remains as a compatibility alias for PR checks.

### Test Runner

```bash
arga test-runner scenarios list --include-presets
arga test-runner scenarios import --file scenario.json
arga test-runner tests list --repo arga-labs/app
arga test-runner tests import --file saved-test.json
arga test-runner tests edit <test_id>
arga test-runner tests run <test_id> --url https://preview.example.com
arga test-runner runs url --url https://demo-app.com --prompt "test login flow"
arga test-runner runs list
arga test-runner runs get <run_id>
arga test-runner runs logs <run_id>
arga test-runner runs rerun <run_id>
arga test-runner runs message <run_id> "Use test@example.com"
```

- `scenarios` supports list/get/create/import/export/update/delete for twin seed scenarios.
- `tests` supports list/get/create/import/export/edit/delete/run for saved browser tests.
- `runs` starts URL runs and inspects live demo-runner history/events.
- `arga test url` and `arga scenarios ...` remain as compatibility aliases.

### TestConfig JSON

Agents should author saved tests by editing TestConfig JSON:

```bash
arga test-runner tests config validate --file test_config.json
arga test-runner tests config summarize --file test_config.json
arga test-runner tests config normalize --file test_config.json --output test_config.json
```

Assertions are intentionally primitive and deterministic:

- `{"type": "text", "contains": "Order confirmed"}`
- `{"type": "url", "contains": "/checkout/success"}`
- `{"type": "visible"}` plus a selector on the step

For URL validation, you can optionally provide credentials:

```bash
arga test-runner runs url \
  --url https://demo-app.com \
  --prompt "log in and create an order" \
  --email test@company.com \
  --password supersecret
```

Both `--email` and `--password` must be supplied together.

### Legacy Validation Runs

```bash
arga runs list --repo arga-labs/validation-server --status running --limit 20
arga runs status <run_id>
arga runs logs <run_id>
arga runs cancel <run_id>
```

- `arga runs list` shows recent PR and branch validation runs in table form.
- `--repo` narrows the list to a single repository.
- `--status` accepts `completed`, `failed`, or `running`. The `running` filter includes non-terminal states such as `queued`.
- `arga runs status <run_id>` prints a detailed summary for a specific run.
- `arga runs logs <run_id>` prints worker logs plus recent runtime logs for a run you own.
- When you omit `<run_id>`, `arga runs logs` falls back to `./.arga-session.json` when present, which makes wizard-created twin sessions easy to inspect from the same directory.
- Add `--json` to `arga runs logs` for a machine-readable response.
- Add `--errors-only` to keep only failed worker logs plus warning/error runtime entries.
- `arga runs cancel <run_id>` cancels the run through the validation API.

Both `runs list` and `runs status` accept `--json` for structured output.

Use `arga test-runner runs ...` for the newer live browser test-runner run history.

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

## JSON Output

Key commands support `--json` for use in CI pipelines, shell scripts, and agent automation:

```bash
# Capture the run ID from a validation
RUN_ID=$(arga test-runner runs url --url https://app.example.com --prompt "test login" --json | jq -r .run_id)

# Poll run status as JSON
arga runs status "$RUN_ID" --json | jq .status

# List runs as a JSON array
arga runs list --repo arga-labs/validation-server --json | jq '.[].run_id'

# Start PR validation and capture result
arga previews pr-checks run --repo arga-labs/validation-server --pr 182 --json
```

Commands that support `--json`:

| Command | JSON shape |
|---|---|
| `arga test-runner runs url` | `{"run_id": "...", "status": "..."}` |
| `arga previews pr-checks run` | `{"run_id": "...", "status": "..."}` |
| `arga previews twins list` | Array of twin catalog items |
| `arga previews twins status <id>` | Full twin provisioning status |
| `arga test-runner tests list` | Array of saved tests |
| `arga test-runner tests run <id>` | Demo runner run object |
| `arga runs status <id>` | Full run object |
| `arga runs list` | Array of run summaries |

## Example Project

See [ArgaLabs/example-app](https://github.com/ArgaLabs/example-app) for a complete working example showing how to integrate Arga into a Next.js project with:

- GitHub Actions CI validation on every PR
- MCP config for Cursor and Claude Code
- A shell script for manual validation
- End-to-end walkthrough in the README

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

## Releasing

This repo includes a GitHub Actions workflow at `.github/workflows/publish.yml` for trusted publishing.

One-time setup:

- Create GitHub Environments named `testpypi` and `pypi` in the repository settings.
- In TestPyPI, add a Trusted Publisher for this GitHub repository and workflow:
  - owner: `ArgaLabs`
  - repository: `arga-cli`
  - workflow: `publish.yml`
  - environment: `testpypi`
- In PyPI, add a Trusted Publisher with the same repository and workflow, but environment `pypi`.

Publishing flow:

- Manual TestPyPI publish: run the `Publish Package` workflow with `repository=testpypi`.
- Automatic PyPI publish: push a tag like `v0.1.0`.
- The workflow verifies that the tag version matches `project.version` in `pyproject.toml`, builds the package with `uv build`, and publishes with `uv publish`.

Typical release steps:

```bash
uv run pytest
git tag v0.1.0
git push origin v0.1.0
```

## Config Storage

The CLI stores its local auth state in:

```bash
~/.config/arga/config.json
```

That file contains the saved API key plus device metadata returned during `arga login`.
