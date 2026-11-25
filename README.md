# Arga CLI

`arga` is the command-line interface for authenticating with Arga, installing MCP configuration into supported coding agents, and managing Twin Runs, Scenarios, Saved Tests, and browser Test Runs.

## What It Does

- Authenticates your machine with Arga using the device login flow.
- Stores a device-scoped API key locally so each terminal/device can be revoked independently.
- Shows the currently authenticated user and workspace.
- Installs MCP configuration into supported local agents.
- Starts Twin Runs and executes browser tests against a reachable application URL.
- Manages test-runner scenarios, saved tests, blocks, and run history.
- Imports, exports, validates, and summarizes agent-editable TestConfig JSON.
- Wraps `git commit` and `git push` with Arga skip-validation helpers.

## Installation 

Install the published package from PyPI:

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

The wizard's `.arga-session.json` stores run metadata and a reference to your
normal CLI login, without copying your API key or proxy token into the project.
Status, reset, extend, teardown, and environment updates use the current login,
including after credential rotation. If setup used an API key without saving a
normal CLI login, the run handle is still saved; run `arga login` with access to
that run before resuming it. Existing sessions with embedded credentials remain
readable, and new session writes omit those credentials.

Install MCP configuration for detected agents:

```bash
arga mcp install
```

Start a new browser test in the [web app](https://app.argalabs.com/test-runs) or through the [Test Runs API](https://docs.argalabs.com/api-reference/browser-agent-create-run). Use the CLI to replay saved flows and inspect results.

Provision twins directly:

```bash
arga twin-runs catalog
TWIN_NAME=your-twin-id
arga twin-runs create --twins "$TWIN_NAME" --wait
arga twin-runs status <run_id>
arga twin-runs extend <run_id> --ttl 90
arga twin-runs lock <run_id>
arga twin-runs reset <run_id>
arga twin-runs teardown <run_id>
```

GitHub includes Actions simulation by default. When the catalog advertises execution, signed-in users can execute supported workflows in the same twin:

```bash
arga twin-runs create --twins github --execute-github-actions --wait
```

The flag requests a private run. See [GitHub Actions](https://docs.argalabs.com/features/github-actions) for setup and supported workflows.

Create and run saved tests:

```bash
arga tests create --name "Checkout" --run-id <demo_run_id> --repo arga-labs/app
arga tests run <test_id> --url https://preview.example.com
```

Any of these commands accept `--json` for machine-parseable output:

```bash
arga tests list --json
arga test-runs get <run_id> --json
```

Inspect historical validation runs:

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
- `arga whoami` verifies the saved API key and prints the authenticated account and plan information.
- `arga logout` removes the local credential and attempts to revoke the current device on the server.

### Choose a generation mode

Use `--generation-mode thorough` for complex prompt requirements when a longer wait is acceptable. Omit the flag for **Fast** generation, or pass `--generation-mode fast` explicitly.

```bash
arga test-runner scenarios create \
  --name "Support escalation" \
  --prompt "A Slack support channel with linked escalation threads and consistent message authors" \
  --twin slack \
  --generation-mode thorough \
  --json

arga twin-runs create \
  --twins slack \
  --scenario-prompt "A support channel with linked escalation threads and consistent message authors" \
  --generation-mode thorough \
  --wait --json
```

Scenario `import` and `update` also accept the flag. It overrides `generation_mode` in the JSON file; without the flag, the file's value is preserved. To regenerate a saved scenario, provide `prompt` in the update file and omit `seed_config`:

```json
{
  "prompt": "A Slack support channel with linked escalation threads and consistent message authors",
  "generation_mode": "thorough"
}
```

```bash
arga test-runner scenarios update <scenario-id> --file scenario-update.json --json
```

The mode applies only to new prompt generation. Saved scenario IDs and explicit seed JSON reuse their existing data. Use `arga test-runner scenarios` for Scenario management. The shorter `arga scenarios` form remains available as an alias.

### Twin Runs

```bash
arga twin-runs catalog
TWIN_NAME=your-twin-id
arga twin-runs create --twins "$TWIN_NAME" --wait
arga twin-runs status <run_id>
arga twin-runs extend <run_id> --ttl 90
arga twin-runs lock <run_id>
arga twin-runs reset <run_id>
arga twin-runs teardown <run_id>
```

- Use a catalog identifier for `TWIN_NAME`. On eligible plans, pass comma-separated identifiers to provision multiple twins in one run.
- Add `--scenario-id` or `--scenario-prompt` to seed state. Add `--private` to require Arga proxy authorization.
- Configure your software with the endpoints and credentials returned by the ready run. `arga twin-runs mcp-config <run_id>` generates client configuration for supported twin MCP endpoints.
- `extend` moves the cleanup deadline, subject to your plan. `reset` restores the provisioning baseline. `teardown` queues cleanup. Poll until the status is `torn_down`.

See the [Twin Run guide](https://docs.argalabs.com/features/twins-quickstart) and [twin reference](https://docs.argalabs.com/concepts/twin-reference) for connection details.

### Compatibility commands

Existing `previews twins` commands remain available as aliases. The former hosted application preview and PR-check setup and start endpoints have been retired. For new workflows, run your application in your own environment and use `twin-runs`, `test-runs`, or `tests`.

### Scenarios, Saved Tests, and browser Test Runs

```bash
arga test-runner scenarios list --include-presets
arga test-runner scenarios import --file scenario.json
arga test-runner scenarios delete <scenario_id>
arga tests list --repo arga-labs/app
arga tests import --file saved-test.json
arga tests edit <test_id>
arga tests run <test_id> --url https://preview.example.com
arga test-runs url --test-config test-config.json --url https://demo-app.com
arga test-runs list
arga test-runs get <run_id>
arga test-runs logs <run_id>
arga test-runs message <run_id> "Use test@example.com"
```

- `scenarios` supports list/presets/get/create/import/export/update/delete for twin seed scenarios. Human-readable
  list/create/import/update output includes the server-recorded creation time; JSON output preserves `created_at`.
- `arga test-runner scenarios presets` lists built-in presets from the public presets API without requiring login.
- `tests` supports list/get/create/import/export/edit/delete/run for saved browser tests.
- `test-runs` replays exported TestConfigs and inspects browser run history. In 0.1.24, prompt-only URL runs call a retired route. Submit a new prompt through the web app or Test Runs API.
- `arga scenarios ...` remains a compatibility alias for `arga test-runner scenarios`.

### TestConfig JSON

Agents should author saved tests by editing TestConfig JSON:

```bash
arga tests config validate --file test_config.json
arga tests config summarize --file test_config.json
arga tests config normalize --file test_config.json --output test_config.json
```

Assertions are intentionally primitive and deterministic:

- `{"type": "text", "contains": "Order confirmed"}`
- `{"type": "url", "contains": "/checkout/success"}`
- `{"type": "visible"}` plus a selector on the step

Use encrypted Saved Test credentials for reusable authenticated flows.

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

Use `arga test-runs` for browser Test Run history.

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
# Start a Saved Test and check its status
RUN_ID=$(arga tests run "$TEST_ID" --url https://app.example.com --json | jq -er .id)
arga test-runs get "$RUN_ID" --json | jq .status
```

Commands that support `--json`:

| Command | JSON shape |
|---|---|
| `arga test-runs url --test-config <file>` | `{"run_id": "...", "status": "..."}` |
| `arga twin-runs catalog` | Array of twin catalog items |
| `arga twin-runs status <id>` | Full twin provisioning status |
| `arga tests list` | Array of saved tests |
| `arga tests run <id>` | Browser test run object |
| `arga runs status <id>` | Full run object |
| `arga runs list` | Array of run summaries |

## Documentation

See the [CLI guide](https://docs.argalabs.com/cli-and-mcp) for setup, supported commands, and examples.

## Using A Custom API URL

By default, the CLI targets `https://api.argalabs.com`.

To point it at another environment, pass `--api-url` or set `ARGA_API_URL`:

```bash
arga login --api-url http://localhost:8000
arga mcp install --api-url http://localhost:8000
arga twin-runs catalog --api-url http://localhost:8000
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

Before each release, run `uv version --bump patch` (or set the intended version
with `uv version X.Y.Z`). Commit both `pyproject.toml` and `uv.lock` with the
features being released, and merge them before tagging. An already published
version cannot distribute later feature changes.

From that merged commit:

```bash
uv run pytest
uv build
git tag "v$(uv version --short)"
git push origin "v$(uv version --short)"
```

## Config Storage

The CLI stores its local auth state in:

```bash
~/.config/arga/config.json
```

That file contains the saved API key plus device metadata returned during `arga login`.

## Fidelity gap reports

Submit one connector's report as UTF-8 Markdown (up to 256 KiB), using your existing
Arga login. The pilot currently supports `linear`, `atlassian`, `microsoft`, and
`google_workspace` when enabled for your account.

```sh
arga fidelity-gaps submit report.md --connector linear --json
arga fidelity-gaps get <report-id> --json
arga fidelity-gaps wait <report-id> --until deployed --timeout 7200 --json
arga fidelity-gaps list --json
```

Include expected and observed behavior, exact API/MCP reproductions, deterministic
seed configuration, and provider contract captures where relevant. Keep credentials
out of reports. Submission returns immediately; work continues after disconnect.
Retrying the same file/context reuses the submission. Use `--idempotency-key` to
set a caller-owned retry key, or `--parent <report-id>` for another report round.

`awaiting_review` means candidate verification, CI and comment gates passed. It does
not mean deployed. `deployed` includes the merged revision and verified image
identities from a fresh Twin Run. Start a new Twin Run before rerunning evals; existing
runs retain their previous images. Record the result with:

```sh
arga fidelity-gaps verify <report-id> --revision <deployed-revision> --outcome passed --json
arga fidelity-gaps submit round-2.md --connector linear --parent <report-id> --json
```

`wait` prints one final JSON object with `--json`. Exit 0 means the requested milestone
was reached, 1 means the job needs information/engineering attention or another
request failed, and 2 means the local polling timeout expired. Timeout never cancels
remote work. This feature requires the fidelity repair backend to be enabled.
