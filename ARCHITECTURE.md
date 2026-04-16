# Architecture

## Design goal

Treat builder and reviewer as interchangeable workers behind a stable contract. The orchestrator should not care whether the builder is Codex and the reviewer is Claude, or the reverse.

It also should not care whether both roles come from the same model family. Same-type pairings such as `codex-builder` + `codex-reviewer` and `claude-builder` + `claude-reviewer` are valid as long as role separation and reviewer constraints are preserved.

## Core entities

### 1. Task spec

The task spec is the only human-authored input both agents should trust.

It should be portable:

- describe the change, not your workstation
- avoid machine-specific paths unless those paths are part of the task itself
- leave repo location, task file location, and permission modes to runtime configuration

It should define:

- objective
- scope
- acceptance criteria
- constraints
- tests expected
- explicit non-goals

### 2. Build report

The builder emits a compact JSON handoff:

- summary
- files touched
- tests run
- known risks
- notes for reviewer

This is a handoff aid, not the source of truth. The source of truth remains the code and diff.

### 3. Review report

The reviewer emits structured findings:

- `approved`
- `summary`
- `blocker_count`
- findings with severity, file, line, title, and detail
- test gaps
- recommended next action

### 4. Human summary

The orchestrator emits a markdown summary at the end of the loop:

- final disposition
- which agents ran
- which permission modes they used
- where the worktree lives
- tests reported
- blocking findings
- explicit escalation note when the loop ends with blockers still open
- recommended human action

### 5. Run archive

Each run is captured under the target repo:

```text
.peer-review/
  runs/
    20260416-201500-add-billing-guardrails/
      task.md
      metadata.json
      round-1.builder.prompt.md
      round-1.builder.response.json
      round-1.diff.patch
      round-1.reviewer.prompt.md
      round-1.reviewer.response.json
      final-summary.md
```

## Isolation model

Default mode should be an isolated worktree.

- base repo stays untouched
- builder and reviewer both point at the same task worktree
- branch is created from the current `HEAD`

This avoids leaking half-finished agent edits into your main checkout.

## Permission model

Permissions should be an explicit part of the run contract.

Humans should be able to set them at two levels:

- defaults in `config/agents.example.json`
- per-run overrides in the launcher request

Per-run values should win when both are present.

Examples:

- Codex builder: `workspace_write`
- Codex reviewer: `read_only`
- Claude builder: `accept_edits`
- Claude reviewer: `plan`

This matters because an unrestricted reviewer stops being a reviewer.

Recommended policy:

- give the builder the minimum edit-capable permission that still lets it complete the task
- keep the reviewer read-only by default
- prefer `plan` for Claude reviewers because it keeps review behavior aligned with the reviewer role

## Why this works

This model separates responsibilities cleanly:

- human owns intent and final approval
- builder owns implementation
- reviewer owns defect discovery
- orchestrator owns repeatability, isolation, and artifact capture

The main failure mode is turning this into agent-to-agent negotiation. That blurs accountability.

## Default loop

1. Record baseline commit.
2. Optionally create task worktree and branch.
3. Run builder with explicit permission profile.
4. Collect diff and diff stat from baseline.
5. Run reviewer with explicit permission profile.
6. If `approved=true`, stop.
7. If blocking findings exist and rounds remain, rerun builder with review JSON.
8. Emit final markdown summary for the human.

## One-agent launcher model

You said you would rather start one agent and have it know to loop in the other.

The reliable way to do that is:

- use a thin launcher instruction layer
- have that launcher call one local orchestrator script
- keep the actual loop in code, not in the live chat thread
- keep the script hidden behind the launching agent so the human entry point stays conversational

### Codex path

Use a Codex skill that tells Codex:

- when to invoke the peer-review flow
- which script to run
- that the script path comes from `AGENT_PEER_REVIEW_TOOLKIT_HOME`
- what minimum arguments must be supplied
- how to summarize the resulting artifacts

### Claude path

Claude does not share Codex's skill system. The normal install path in this repo is the Markdown subagent under `.claude/agents/`. An optional custom-agent JSON example is also included for teams that manage their own startup wrapper or agent catalog. Both launch paths should call the same local orchestrator script, resolved from `AGENT_PEER_REVIEW_TOOLKIT_HOME`, so behavior stays aligned.

## Failure modes to guard against

### 1. Reviewer becomes vague

Fix: schema-enforced findings plus file references.

### 2. Builder overstates confidence

Fix: tests-run field must list only commands actually executed.

### 3. Infinite loop

Fix: hard round cap.

### 3a. Round cap hides unresolved blockers

Fix: if the last allowed review still reports blockers, emit an explicit escalation note in the final summary and JSON output.

### 4. Main checkout gets polluted

Fix: default to worktree mode.

### 5. Reviewer silently edits

Fix: explicit reviewer permission profile set to read-only or `plan`.
