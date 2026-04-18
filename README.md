# Agent Peer Review

This is a reference scaffold for running two coding agents in fixed roles:

- one agent builds
- one agent reviews
- the builder can revise from structured findings
- a human owns final merge

The stable contract is:

1. task spec
2. build report
3. git diff
4. structured review report
5. human summary

That is what keeps the loop disciplined.

## Quick Start

1. Clone this repo anywhere.
2. Set:

```bash
export AGENT_PEER_REVIEW_TOOLKIT_HOME=/path/to/agent-peer-review
```

3. Choose default builder and reviewer permissions in `config/agents.example.json`.
4. Install the Codex skill or Claude subagent from the `Setup` section below.
5. Launch `codex` or `claude`.
6. Ask that agent to use the peer-review process with:
   - the target repo
   - the task spec path
   - the builder and reviewer identities
   - optional per-run permission overrides
7. Let the launching agent orchestrate the loop internally and return the final summary.

Start from these example prompts:

- Codex: `examples/start-from-codex.md`
- Claude: `examples/start-from-claude.md`

## Recommended operating model

Do not let the same agent both implement and approve in one pass.

- Builder responsibilities:
  - interpret the task spec
  - edit code
  - run validation where practical
  - emit a JSON build report
- Reviewer responsibilities:
  - inspect repo state plus diff
  - identify correctness issues, regressions, risky assumptions, and missing tests
  - emit a JSON review report
  - stay read-only by default, with Claude reviewers preferring `plan`

## Supported Pairings

The workflow supports both mixed-model and same-model pairings.

Examples:

- `codex-builder` + `claude-reviewer`
- `claude-builder` + `codex-reviewer`
- `codex-builder` + `codex-reviewer`
- `claude-builder` + `claude-reviewer`

The important requirement is role separation, not vendor separation:

- the builder and reviewer should be different roles
- the reviewer should stay constrained
- the handoff should stay structured

Using different model families can give you a more independent second opinion. Using the same model family still works, as long as the reviewer prompt, permissions, and artifact contract are strict.

## New capabilities in this scaffold

- Per-agent permission profiles
  - Codex and Claude profiles can each run under explicit permission modes
  - defaults live in `config/agents.example.json`
  - each run can override those defaults explicitly
- Optional isolated worktree mode
  - Builder and reviewer can operate in a disposable task worktree instead of your main checkout
- Human-readable handoff
  - Every run ends with a markdown summary for fast merge decisions
  - If the final allowed review still has blocking feedback, the summary calls that out explicitly as an escalation
- Runtime progress reporting
  - The orchestrator emits stage changes and periodic heartbeats while builder or reviewer runs are in flight
  - Long review passes should no longer look silent from the parent agent
- One-agent orchestration entry points
  - A Codex skill is included
  - A Claude custom-agent example is included

## Portability

This repo is meant to be cloned anywhere. It should not depend on the author's local paths.

- Use `AGENT_PEER_REVIEW_TOOLKIT_HOME` to point launchers at this checkout
- Pass the target repo and task spec as runtime inputs
- Keep task specs portable and free of machine-specific paths unless a path is the thing being changed

## Permission model

Humans choose permissions at two levels:

- default permissions
  - configured once in `config/agents.example.json`
- per-run permissions
  - passed in the launch request for that specific task

The orchestrator supports both. If a run includes `builder permission` or `reviewer permission`, that run overrides the configured default. If the run does not include them, the configured defaults are used.

Recommended policy:

- builder
  - give the builder the minimum edit-capable permission that still lets it do the work for that task
- reviewer
  - keep the reviewer read-only by default
  - prefer `read_only` for Codex reviewers
  - prefer `plan` for Claude reviewers

Current example defaults in `config/agents.example.json`:

- `codex-builder`: `workspace_write`
- `codex-reviewer`: `read_only`
- `claude-builder`: `accept_edits`
- `claude-reviewer`: `plan`

Other useful defaults in the same file:

- `default_rounds`
  - max builder/reviewer passes before the run escalates to a human
- `default_agent_timeout_seconds`
  - per-agent timeout so a hung CLI does not stall the whole orchestrator
- `default_agent_heartbeat_seconds`
  - heartbeat interval for in-flight builder or reviewer progress updates

## Setup

### 1. Configure the toolkit path

Set:

```bash
export AGENT_PEER_REVIEW_TOOLKIT_HOME=/path/to/agent-peer-review
```

### 2. Choose your default permissions

Copy or adapt:

- `config/agents.example.json`

This file is where you set default builder and reviewer permissions for your machine or team. Those defaults apply whenever a run request does not specify permissions explicitly.

You can still override either role on a specific run by including:

- `builder permission: ...`
- `reviewer permission: ...`

Use that for task-specific risk control. For example, keep a permissive builder default for local work, but drop a particular run to a narrower permission mode.

If you want to inspect the exact resolved builder and reviewer commands before letting the agents touch a repo, use `--dry-run` when invoking `scripts/peer_review.py` directly or have the launching agent do an internal dry run first.

### 3. Install a launcher

Install the Codex skill and/or Claude subagent if you want the one-agent launcher flow.

### Codex Skill

This repo ships a Codex skill here:

- `skill/peer-review-orchestrator/`

Install it into your local Codex skills directory:

```bash
mkdir -p ~/.codex/skills
ln -sfn "$AGENT_PEER_REVIEW_TOOLKIT_HOME/skill/peer-review-orchestrator" \
  ~/.codex/skills/peer-review-orchestrator
```

After that, start `codex` and ask it to use the peer-review process. The skill gives Codex the workflow and tells it to run the internal orchestrator itself.

### Claude Package

Anthropic officially supports user-level and project-level subagents stored under `.claude/agents/`.

This repo includes a Claude-friendly package here:

- `claude-package/.claude/agents/peer-review-orchestrator.md`

You can install it either:

- globally, by copying it into `~/.claude/agents/`
- per-project, by copying it into `<target-repo>/.claude/agents/`

For a global install:

```bash
mkdir -p ~/.claude/agents
cp "$AGENT_PEER_REVIEW_TOOLKIT_HOME/claude-package/.claude/agents/peer-review-orchestrator.md" \
  ~/.claude/agents/peer-review-orchestrator.md
```

See `claude-package/README.md` for the exact steps.

### Optional Claude custom-agent JSON

This repo also includes:

- `config/claude-agents.example.json`

Use that file only if you want to manage Claude through your own custom-agent catalog or startup wrapper. Most users do not need it for day-to-day use. The simpler path is the Markdown subagent install under `.claude/agents/`.

## Sanity Check

Before relying on the workflow, verify three things:

1. Your shell can see the toolkit path:

```bash
echo "$AGENT_PEER_REVIEW_TOOLKIT_HOME"
```

2. Codex can see the skill:

```bash
ls -la ~/.codex/skills/peer-review-orchestrator
```

3. Claude can see the subagent:

```bash
ls -la ~/.claude/agents/peer-review-orchestrator.md
```

If you just added the environment variable, reload your shell first:

```bash
source ~/.zshrc
```

### Codex Smoke Test

Start `codex` and paste:

```text
Use the peer-review process for a small test task.

- repo: /path/to/some-project
- task: /path/to/task.md
- builder: codex-builder
- reviewer: codex-reviewer
- builder permission: workspace_write
- reviewer permission: read_only
- create worktree: yes

Use the installed peer-review skill yourself. Do not ask me to run a Python command manually.
```

Expected result:

- Codex recognizes the peer-review workflow
- Codex does not ask you to invoke `scripts/peer_review.py` yourself
- Codex gathers or confirms the repo, task, permissions, and pairing

### Claude Smoke Test

Start `claude` and paste:

```text
Use the peer-review process for a small test task.

- repo: /path/to/some-project
- task: /path/to/task.md
- builder: claude-builder
- reviewer: claude-reviewer
- builder permission: accept_edits
- reviewer permission: plan
- create worktree: yes

Use the installed peer-review subagent yourself. Do not ask me to run a Python command manually.
```

Expected result:

- Claude recognizes the peer-review workflow
- Claude does not ask you to invoke `scripts/peer_review.py` yourself
- Claude gathers or confirms the repo, task, permissions, and pairing

### Optional Live CLI Integration Checks

The default unit suite does not require authenticated agent CLIs. If you want to verify the real Codex and Claude integrations on a machine that has both CLIs installed and authenticated, run:

```bash
CI_HAS_CLI_AGENTS=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
```

That adds gated live checks for:

- Claude's JSON envelope plus `structured_output` extraction
- Codex acceptance of `schemas/review-report.schema.json`

## Troubleshooting

### `AGENT_PEER_REVIEW_TOOLKIT_HOME` is unset

- run `echo "$AGENT_PEER_REVIEW_TOOLKIT_HOME"`
- if empty, export it and reload your shell
- if you added it to a shell profile, run `source ~/.zshrc` or open a new shell

### Codex does not see the skill

- verify `~/.codex/skills/peer-review-orchestrator` exists
- if it is a symlink, make sure it points at `skill/peer-review-orchestrator/`
- restart `codex` after installing or updating the skill

### Claude does not see the subagent

- verify `~/.claude/agents/peer-review-orchestrator.md` exists for a global install
- for a per-project install, verify `<target-repo>/.claude/agents/peer-review-orchestrator.md`
- restart `claude` after installing or updating the subagent

### The CLI is not authenticated or not installed

- confirm `codex` or `claude` is on your `PATH`
- run the CLI directly once outside this workflow and finish any auth flow first
- do not debug the peer-review loop until the underlying CLI can run normally on its own

### The agent returns invalid JSON or schema validation fails

- inspect the saved `*.stdout.txt` and `*.stderr.txt` artifacts in `.peer-review/runs/...`
- rerun with the reviewer kept read-only and the prompt kept explicit
- if you edited the schemas or prompt templates, validate those changes before blaming the agent CLI

### Permission errors on a run

- check whether the run explicitly overrode permissions
- if not, inspect the defaults in `config/agents.example.json`
- widen only the role that needs it
- keep the reviewer read-only unless you intentionally want a different policy

### A run hangs or an agent never returns

- inspect `default_agent_timeout_seconds` in `config/agents.example.json`
- raise it only if the CLI genuinely needs more time
- use `--dry-run` first if you want to confirm the exact command and repo path being used

## Layout

- `config/agents.example.json`
  - agent command templates, permission profiles, and output extraction paths
- `config/claude-agents.example.json`
  - optional Claude custom-agent example for teams that manage a custom-agent catalog
- `claude-package/`
  - Claude-friendly package with a ready-to-install subagent under `.claude/agents/`
- `prompts/`
  - builder and reviewer prompt shells
- `schemas/`
  - JSON schemas for build and review handoffs
- `scripts/peer_review.py`
  - orchestrates build -> review -> optional revision
- `skill/peer-review-orchestrator/`
  - Codex skill that tells Codex how to invoke the orchestrator
- `examples/task-template.md`
  - task spec template
- `examples/start-from-codex.md`
  - example command/request when launching from Codex
- `examples/start-from-claude.md`
  - example command/request when launching from Claude

## User-Facing Entry Point

Humans should start this workflow by launching `codex` or `claude` and asking that agent to use the peer-review process.

- Preferred Codex entry point:
  - use the request in `examples/start-from-codex.md`
- Preferred Claude entry point:
  - use the request in `examples/start-from-claude.md`

The human should not be expected to invoke `scripts/peer_review.py` directly. The launching agent should do that internally after it understands the requested builder, reviewer, permissions, repo, and task spec.

## Starting from one agent instead of calling the script directly

### Starting from Codex

Install or symlink the included skill, set `AGENT_PEER_REVIEW_TOOLKIT_HOME`, then ask Codex to run the peer-review loop. The skill tells Codex to use the local orchestrator script instead of improvising the loop.

### Starting from Claude

Claude does not use Codex-style skills. The normal path is the bundled Markdown subagent under `claude-package/.claude/agents/`.

Use `config/claude-agents.example.json` only if you want to manage Claude through your own custom-agent catalog or startup wrapper. Otherwise, install the Markdown subagent and start Claude normally.

## Internal Implementation

`scripts/peer_review.py` is an internal orchestrator, not the human-facing interface.

Its job is to give the launching agent a stable implementation for:

- worktree creation
- builder/reviewer sequencing
- permission profile handling
- run artifact capture
- final escalation and summary output

## What this scaffold assumes

- `codex` and `claude` CLIs are installed
- both CLIs are authenticated
- the target repo is a git repo
- you want a human checkpoint before merge
- each user configures their own local checkout path through `AGENT_PEER_REVIEW_TOOLKIT_HOME`

## What I would not do

- I would not let the reviewer edit on the first pass.
- I would not pass only natural-language summaries between agents without the diff.
- I would not forward the entire prior transcript by default.
- I would not run unlimited fix/review loops.

## Suggested production flow

1. Human writes or approves the task spec.
2. Orchestrator creates a task worktree unless you explicitly choose in-place mode.
3. Builder runs with its configured permission profile.
4. Reviewer runs with its configured permission profile, usually read-only.
5. If blocking findings exist, builder gets one or two revision rounds.
6. If the final allowed review still has blockers, the summary marks the run as escalated and not merge-ready.
7. Human reads the final markdown summary and merges or rejects.
