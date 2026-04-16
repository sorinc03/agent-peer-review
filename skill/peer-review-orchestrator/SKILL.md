---
name: peer-review-orchestrator
description: Use when the user wants one coding agent to build and the other to review, or wants to start Codex and have it coordinate a builder/reviewer loop through the local agent peer-review scaffold. This skill runs the local orchestrator script, prefers isolated worktrees, requires explicit builder and reviewer identities plus permission modes, and returns the final markdown summary.
---

# Peer Review Orchestrator

Use this skill when the user wants a two-agent build/review workflow.

The human-facing entry point is the conversation with Codex, not a shell command.

## Workflow

1. Confirm or infer:
   - target repo
   - task spec path
   - builder profile
   - reviewer profile
   - builder permission
   - reviewer permission
   - whether to create a worktree
2. Prefer worktree mode unless the user explicitly asks to operate in-place.
3. Run:

```bash
python3 "$AGENT_PEER_REVIEW_TOOLKIT_HOME/scripts/peer_review.py" \
  --repo <repo> \
  --task <task> \
  --builder <builder-profile> \
  --reviewer <reviewer-profile> \
  --builder-permission <builder-permission> \
  --reviewer-permission <reviewer-permission> \
  [--create-worktree]
```

4. Read the generated `final-summary.md` from the run artifact directory.
5. Summarize the result for the user and make the human checkpoint explicit.

If `AGENT_PEER_REVIEW_TOOLKIT_HOME` is not set, stop and ask the user to configure it for their machine.

## Defaults

- Prefer `codex-builder` + `claude-reviewer` unless the user asks otherwise.
- Prefer builder permission that allows edits.
- Prefer reviewer permission that keeps the reviewer read-only.
- Prefer `--create-worktree`.

## Do not do this

- Do not improvise an unbounded agent conversation loop in chat.
- Do not ask the human to run the orchestrator script manually.
- Do not let the reviewer edit on the first pass unless the user explicitly changes the policy.
- Do not skip the final markdown summary.
