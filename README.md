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

3. Launch `codex` or `claude`.
4. Ask that agent to use the peer-review process with:
   - the target repo
   - the task spec path
   - the builder and reviewer identities
   - the builder and reviewer permission modes
5. Let the launching agent orchestrate the loop internally and return the final summary.

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
  - stay read-only by default

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
- Optional isolated worktree mode
  - Builder and reviewer can operate in a disposable task worktree instead of your main checkout
- Human-readable handoff
  - Every run ends with a markdown summary for fast merge decisions
  - If the final allowed review still has blocking feedback, the summary calls that out explicitly as an escalation
- One-agent orchestration entry points
  - A Codex skill is included
  - A Claude custom-agent example is included

## Portability

This repo is meant to be cloned anywhere. It should not depend on the author's local paths.

- Use `AGENT_PEER_REVIEW_TOOLKIT_HOME` to point launchers at this checkout
- Pass the target repo and task spec as runtime inputs
- Keep task specs portable and free of machine-specific paths unless a path is the thing being changed

## Setup

1. Clone this repo anywhere.
2. Set:

```bash
export AGENT_PEER_REVIEW_TOOLKIT_HOME=/path/to/agent-peer-review
```

3. Copy or adapt:
   - `config/agents.example.json`
   - `config/claude-agents.example.json`
4. Install the Codex skill and/or Claude subagent if you want the one-agent launcher flow.

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
- reviewer permission: default
- create worktree: yes

Use the installed peer-review subagent yourself. Do not ask me to run a Python command manually.
```

Expected result:

- Claude recognizes the peer-review workflow
- Claude does not ask you to invoke `scripts/peer_review.py` yourself
- Claude gathers or confirms the repo, task, permissions, and pairing

## Layout

- `config/agents.example.json`
  - agent command templates and permission profiles
- `config/claude-agents.example.json`
  - Claude custom-agent example for orchestration
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

Claude does not use Codex-style skills. Its closest equivalent is a custom agent definition. The example in `config/claude-agents.example.json` is the right shape: set `AGENT_PEER_REVIEW_TOOLKIT_HOME`, start Claude with that agent, and ask it to run the peer-review loop.

The repo also includes a Claude-friendly package using Anthropic's documented `.claude/agents/` subagent format for easier installation and sharing.

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
