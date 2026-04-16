# Claude Package

This directory contains a Claude Code-friendly package built around Anthropic's documented subagent format.

## Why this exists

Anthropic officially supports subagents stored as Markdown files with YAML frontmatter in:

- `~/.claude/agents/` for user-level agents
- `.claude/agents/` for project-level agents

This repo ships the peer-review orchestrator in that format so users can install it directly today, without waiting on a separate plugin marketplace packaging step.

For most users, this Markdown subagent is the right Claude integration point. The separate `config/claude-agents.example.json` file in the repo is only for teams that already manage Claude through a custom-agent catalog or startup wrapper.

## Included file

- `.claude/agents/peer-review-orchestrator.md`

## Install globally

```bash
mkdir -p ~/.claude/agents
cp claude-package/.claude/agents/peer-review-orchestrator.md ~/.claude/agents/
```

## Install into a target repo

```bash
mkdir -p /path/to/target-repo/.claude/agents
cp claude-package/.claude/agents/peer-review-orchestrator.md /path/to/target-repo/.claude/agents/
```

## Notes

- Set `AGENT_PEER_REVIEW_TOOLKIT_HOME` on your machine before using the subagent.
- Default builder and reviewer permissions live in `config/agents.example.json`.
- A specific run can still override either role by including `builder permission: ...` or `reviewer permission: ...` in the request.
- Keep the reviewer read-only by default. If Claude is the reviewer, prefer `plan`.
- The human-facing entry point is still conversational: start `claude`, then ask it to use the peer-review process.
- This package is intentionally simple and aligned with Anthropic's documented subagent format. If Anthropic stabilizes a richer public plugin packaging standard or marketplace manifest flow, this repo can wrap the same orchestrator with that packaging later.
