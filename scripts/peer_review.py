#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run(
    cmd: list[str],
    *,
    cwd: Path,
    stdin: str | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )


def git(repo: Path, *args: str) -> str:
    result = run(["git", *args], cwd=repo)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout.strip()


def extract_json(raw: str) -> Any:
    text = raw.strip()
    if not text:
        raise ValueError("Agent returned empty output")

    try:
        return json.loads(text)
    except JSONDecodeError as original_error:
        for candidate in iter_json_object_candidates(text):
            try:
                return json.loads(candidate)
            except JSONDecodeError:
                continue
        raise ValueError("Could not extract a valid JSON object from agent output") from original_error


def iter_json_object_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if start is None:
            if char == "{":
                start = index
                depth = 1
                in_string = False
                escaped = False
            continue

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidates.append(text[start : index + 1])
                start = None

    return candidates


def render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def materialize_command(template: list[str], values: dict[str, str]) -> list[str]:
    command: list[str] = []
    for part in template:
        rendered = part
        for key, value in values.items():
            rendered = rendered.replace(f"{{{key}}}", value)
        command.append(rendered)
    return command


def splice_args(command: list[str], extra_args: list[str]) -> list[str]:
    if command and command[-1] == "-":
        return [*command[:-1], *extra_args, command[-1]]
    return [*command, *extra_args]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "task"


def build_run_id(timestamp: str, slug: str) -> str:
    return f"{timestamp}-{slug}-{secrets.token_hex(3)}"


def build_command(
    *,
    profile_name: str,
    profiles: dict[str, Any],
    repo: Path,
    schema_path: Path,
    permission_name: str | None,
) -> tuple[list[str], str]:
    profile = profiles[profile_name]
    schema_inline = json.dumps(json.loads(read_text(schema_path)))
    permission = permission_name or profile.get("default_permission")
    permission_profiles = profile.get("permission_profiles", {})
    if permission not in permission_profiles:
        available = ", ".join(sorted(permission_profiles))
        raise ValueError(f"Unknown permission profile '{permission}' for {profile_name}. Available: {available}")

    base_command = materialize_command(
        profile["command"],
        {
            "repo": str(repo),
            "schema_path": str(schema_path),
            "schema_inline": schema_inline,
        },
    )
    return splice_args(base_command, permission_profiles[permission]), permission


def extract_profile_payload(payload: Any, profile: dict[str, Any]) -> dict[str, Any]:
    path = profile.get("output_extract_path", [])
    current = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"Could not extract structured output via path: {path}")
        current = current[key]

    if not isinstance(current, dict):
        raise ValueError("Extracted structured output is not a JSON object")
    return current


def invoke_agent(
    *,
    repo: Path,
    profile_name: str,
    profiles: dict[str, Any],
    schema_path: Path,
    prompt: str,
    artifact_dir: Path,
    prefix: str,
    permission_name: str | None,
    timeout_seconds: int | None,
) -> tuple[dict[str, Any], str]:
    profile = profiles[profile_name]
    command, resolved_permission = build_command(
        profile_name=profile_name,
        profiles=profiles,
        repo=repo,
        schema_path=schema_path,
        permission_name=permission_name,
    )

    write_text(artifact_dir / f"{prefix}.command.txt", " ".join(shlex.quote(part) for part in command) + "\n")
    write_text(artifact_dir / f"{prefix}.prompt.md", prompt)

    try:
        result = run(command, cwd=repo, stdin=prompt, timeout_seconds=timeout_seconds)
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "").rstrip()
        if stderr:
            stderr += "\n"
        stderr += f"Timed out after {timeout_seconds} seconds.\n"
        write_text(artifact_dir / f"{prefix}.stdout.txt", stdout)
        write_text(artifact_dir / f"{prefix}.stderr.txt", stderr)
        raise RuntimeError(
            f"{profile_name} timed out after {timeout_seconds} seconds.\n"
            f"See {artifact_dir / f'{prefix}.stderr.txt'}"
        ) from exc

    write_text(artifact_dir / f"{prefix}.stdout.txt", stdout)
    write_text(artifact_dir / f"{prefix}.stderr.txt", stderr)

    if result.returncode != 0:
        raise RuntimeError(
            f"{profile_name} failed with exit code {result.returncode}.\n"
            f"See {artifact_dir / f'{prefix}.stderr.txt'}"
        )

    envelope = extract_json(stdout)
    payload = extract_profile_payload(envelope, profile)
    write_text(artifact_dir / f"{prefix}.response.json", json.dumps(payload, indent=2) + "\n")
    if payload is not envelope:
        write_text(artifact_dir / f"{prefix}.envelope.json", json.dumps(envelope, indent=2) + "\n")
    return payload, resolved_permission


def build_worktree_plan(
    base_repo: Path,
    *,
    run_id: str,
    requested_root: str | None,
) -> tuple[Path, str]:
    root = Path(os.path.expanduser(requested_root)).resolve() if requested_root else base_repo / ".peer-review-worktrees"
    branch = f"peer-review/{run_id}"
    worktree_path = root / run_id
    return worktree_path, branch


def create_worktree(base_repo: Path, *, run_id: str, requested_root: str | None) -> tuple[Path, str]:
    worktree_path, branch = build_worktree_plan(
        base_repo,
        run_id=run_id,
        requested_root=requested_root,
    )
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    result = run(["git", "worktree", "add", "-b", branch, str(worktree_path), "HEAD"], cwd=base_repo)
    if result.returncode != 0:
        raise RuntimeError(f"git worktree add failed:\n{result.stderr}")

    return worktree_path, branch


def diff_no_index(repo: Path, path: str, *, stat: bool) -> str:
    cmd = ["git", "diff", "--no-index"]
    if stat:
        cmd.append("--stat")
    cmd.extend(["--", "/dev/null", path])
    result = run(cmd, cwd=repo)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git diff --no-index failed for {path}:\n{result.stderr}")
    return result.stdout.strip()


def collect_diff(repo: Path, baseline: str) -> tuple[str, str, str]:
    diff_stat = git(repo, "diff", "--stat", baseline)
    diff_patch = git(repo, "diff", "--patch", baseline)
    status_short = git(repo, "status", "--short")
    untracked = [line[3:] for line in status_short.splitlines() if line.startswith("?? ")]

    for rel_path in untracked:
        extra_stat = diff_no_index(repo, rel_path, stat=True)
        extra_patch = diff_no_index(repo, rel_path, stat=False)
        if extra_stat:
            diff_stat = f"{diff_stat}\n{extra_stat}".strip()
        if extra_patch:
            diff_patch = f"{diff_patch}\n{extra_patch}".strip()

    return diff_stat, diff_patch, status_short


def collect_round_metadata(
    *,
    round_number: int,
    build_report: dict[str, Any],
    builder_profile: str,
    builder_permission: str,
    reviewer_profile: str,
    reviewer_permission: str,
    review_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_number,
        "builder_profile": builder_profile,
        "builder_permission": builder_permission,
        "reviewer_profile": reviewer_profile,
        "reviewer_permission": reviewer_permission,
        "build_report": build_report,
        "review_report": review_report,
    }


def build_markdown_summary(
    *,
    repo: Path,
    repo_for_run: Path,
    artifact_dir: Path,
    baseline: str,
    worktree_branch: str | None,
    status_short: str,
    builder: str,
    reviewer: str,
    builder_permission: str,
    reviewer_permission: str,
    create_worktree_enabled: bool,
    final_review: dict[str, Any] | None,
    rounds: list[dict[str, Any]],
    max_rounds: int,
    rounds_completed: int,
    loop_exhausted_with_blockers: bool,
) -> str:
    approved = bool(final_review and final_review.get("approved"))
    next_action = final_review.get("next_action") if final_review else "escalate_to_human"
    disposition = "approved" if approved or next_action == "approve" else "changes requested"
    blocker_count = int(final_review.get("blocker_count", 0)) if final_review else 0

    tests_run: list[str] = []
    for item in rounds:
        for test in item["build_report"].get("tests_run", []):
            if test not in tests_run:
                tests_run.append(test)

    findings = final_review.get("findings", []) if final_review else []
    lines = [
        "# Final Summary",
        "",
        f"- Disposition: {disposition}",
        f"- Repo: {repo}",
        f"- Execution checkout: {repo_for_run}",
        f"- Baseline commit: {baseline}",
        f"- Worktree mode: {'yes' if create_worktree_enabled else 'no'}",
        f"- Worktree branch: {worktree_branch or 'n/a'}",
        f"- Builder: {builder} ({builder_permission})",
        f"- Reviewer: {reviewer} ({reviewer_permission})",
        f"- Rounds completed: {rounds_completed}/{max_rounds}",
        f"- Artifact dir: {artifact_dir}",
        f"- Final git status: {'clean' if not status_short else 'dirty'}",
        f"- Blocking findings outstanding: {'yes' if blocker_count > 0 else 'no'}",
        "",
        "## Review Summary",
        "",
        final_review.get("summary", "No final review summary available.") if final_review else "No final review summary available.",
        "",
    ]

    if loop_exhausted_with_blockers:
        lines.extend(
            [
                "## Escalation",
                "",
                f"- The loop hit its round limit ({max_rounds}) with blocking reviewer feedback still open.",
                "- Do not merge from this run without a human explicitly accepting the remaining issues.",
                "",
            ]
        )

    lines.extend(
        [
        "## Tests Reported",
        "",
        ]
    )

    if tests_run:
        lines.extend(f"- {test}" for test in tests_run)
    else:
        lines.append("- No tests reported")

    lines.extend(["", "## Blocking Findings", ""])
    if findings:
        for finding in findings:
            location = ""
            if finding.get("file"):
                location = f" ({finding['file']}"
                if finding.get("line"):
                    location += f":{finding['line']}"
                location += ")"
            lines.append(f"- [{finding.get('severity', 'unknown')}] {finding.get('title', 'Untitled')}{location}: {finding.get('detail', '')}")
    else:
        lines.append("- No findings recorded")

    lines.extend(["", "## Recommended Human Action", ""])
    if approved or next_action == "approve":
        lines.append("- Read the diff and merge if it matches your intent.")
    elif next_action == "revise":
        lines.append("- Do not merge yet. Another builder pass or a human fix is required.")
    else:
        lines.append("- Escalate to a human. The loop did not resolve the task cleanly.")

    return "\n".join(lines) + "\n"


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(description="Run a builder/reviewer loop with Codex and Claude.")
    parser.add_argument("--repo", required=True, help="Target git repository")
    parser.add_argument("--task", required=True, help="Markdown task spec")
    parser.add_argument("--builder", required=True, help="Agent profile name for builder")
    parser.add_argument("--reviewer", required=True, help="Agent profile name for reviewer")
    parser.add_argument("--builder-permission", default=None, help="Permission profile for builder")
    parser.add_argument("--reviewer-permission", default=None, help="Permission profile for reviewer")
    parser.add_argument("--rounds", type=int, default=None, help="Maximum build/review rounds")
    parser.add_argument("--agent-timeout-seconds", type=int, default=None, help="Timeout per agent invocation in seconds")
    parser.add_argument("--create-worktree", action="store_true", help="Create an isolated git worktree for the run")
    parser.add_argument("--worktree-root", default=None, help="Directory under which task worktrees should be created")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved run plan and commands without executing agents")
    parser.add_argument(
        "--config",
        default=str(root / "config" / "agents.example.json"),
        help="Path to agent config JSON",
    )
    args = parser.parse_args()

    base_repo = Path(os.path.expanduser(args.repo)).resolve()
    task_path = Path(os.path.expanduser(args.task)).resolve()
    config_path = Path(os.path.expanduser(args.config)).resolve()

    if not (base_repo / ".git").exists():
        raise SystemExit(f"{base_repo} is not a git repository")

    config = json.loads(read_text(config_path))
    profiles = config["profiles"]
    for name in (args.builder, args.reviewer):
        if name not in profiles:
            raise SystemExit(f"Unknown agent profile: {name}")

    max_rounds = int(config.get("default_rounds", 2)) if args.rounds is None else args.rounds
    if max_rounds < 1:
        raise SystemExit("--rounds must be at least 1")

    agent_timeout_seconds = (
        int(config.get("default_agent_timeout_seconds", 1800))
        if args.agent_timeout_seconds is None
        else args.agent_timeout_seconds
    )
    if agent_timeout_seconds < 1:
        raise SystemExit("--agent-timeout-seconds must be at least 1")

    task_spec = read_text(task_path)
    baseline = git(base_repo, "rev-parse", "HEAD")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = slugify(task_path.stem)
    run_id = build_run_id(timestamp, slug)

    repo_for_run = base_repo
    worktree_branch: str | None = None
    planned_worktree_path: Path | None = None
    if args.create_worktree:
        planned_worktree_path, worktree_branch = build_worktree_plan(
            base_repo,
            run_id=run_id,
            requested_root=args.worktree_root,
        )
        repo_for_run = planned_worktree_path
        if not args.dry_run:
            repo_for_run, worktree_branch = create_worktree(
                base_repo,
                run_id=run_id,
                requested_root=args.worktree_root,
            )

    artifact_dir = base_repo / ".peer-review" / "runs" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_text(artifact_dir / "task.md", task_spec)

    metadata = {
        "repo": str(base_repo),
        "repo_for_run": str(repo_for_run),
        "baseline": baseline,
        "builder": args.builder,
        "reviewer": args.reviewer,
        "builder_permission_requested": args.builder_permission,
        "reviewer_permission_requested": args.reviewer_permission,
        "agent_timeout_seconds": agent_timeout_seconds,
        "create_worktree": args.create_worktree,
        "worktree_branch": worktree_branch,
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "dry_run": args.dry_run,
    }
    write_text(artifact_dir / "metadata.json", json.dumps(metadata, indent=2) + "\n")

    builder_template = read_text(root / "prompts" / "builder.md")
    reviewer_template = read_text(root / "prompts" / "reviewer.md")
    build_schema_path = root / "schemas" / "build-report.schema.json"
    review_schema_path = root / "schemas" / "review-report.schema.json"

    builder_preview_command, final_builder_permission = build_command(
        profile_name=args.builder,
        profiles=profiles,
        repo=repo_for_run,
        schema_path=build_schema_path,
        permission_name=args.builder_permission,
    )
    reviewer_preview_command, final_reviewer_permission = build_command(
        profile_name=args.reviewer,
        profiles=profiles,
        repo=repo_for_run,
        schema_path=review_schema_path,
        permission_name=args.reviewer_permission,
    )

    if args.dry_run:
        summary = {
            "repo": str(base_repo),
            "repo_for_run": str(repo_for_run),
            "baseline": baseline,
            "builder": args.builder,
            "reviewer": args.reviewer,
            "builder_permission": final_builder_permission,
            "reviewer_permission": final_reviewer_permission,
            "agent_timeout_seconds": agent_timeout_seconds,
            "worktree_branch": worktree_branch,
            "create_worktree": args.create_worktree,
            "artifact_dir": str(artifact_dir),
            "builder_command": builder_preview_command,
            "reviewer_command": reviewer_preview_command,
            "dry_run": True,
        }
        write_text(artifact_dir / "dry-run.json", json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
        return 0

    review_findings = ""
    last_review: dict[str, Any] | None = None
    round_summaries: list[dict[str, Any]] = []
    final_status_short = ""
    rounds_completed = 0

    for round_number in range(1, max_rounds + 1):
        rounds_completed = round_number
        builder_prompt = render_template(
            builder_template,
            {
                "TASK_SPEC": task_spec,
                "REPO": str(repo_for_run),
                "BASELINE": baseline,
                "REVIEW_FINDINGS": review_findings or "No prior review findings.",
            },
        )

        build_report, final_builder_permission = invoke_agent(
            repo=repo_for_run,
            profile_name=args.builder,
            profiles=profiles,
            schema_path=build_schema_path,
            prompt=builder_prompt,
            artifact_dir=artifact_dir,
            prefix=f"round-{round_number}.builder",
            permission_name=args.builder_permission,
            timeout_seconds=agent_timeout_seconds,
        )

        diff_stat, diff_patch, final_status_short = collect_diff(repo_for_run, baseline)
        write_text(artifact_dir / f"round-{round_number}.diff.stat", diff_stat + ("\n" if diff_stat else ""))
        write_text(artifact_dir / f"round-{round_number}.diff.patch", diff_patch)
        write_text(artifact_dir / f"round-{round_number}.status.txt", final_status_short + ("\n" if final_status_short else ""))

        reviewer_prompt = render_template(
            reviewer_template,
            {
                "TASK_SPEC": task_spec,
                "BUILD_REPORT": json.dumps(build_report, indent=2),
                "DIFF_STAT": diff_stat or "No diff stat available.",
                "DIFF_PATCH": diff_patch or "No patch available.",
            },
        )

        last_review, final_reviewer_permission = invoke_agent(
            repo=repo_for_run,
            profile_name=args.reviewer,
            profiles=profiles,
            schema_path=review_schema_path,
            prompt=reviewer_prompt,
            artifact_dir=artifact_dir,
            prefix=f"round-{round_number}.reviewer",
            permission_name=args.reviewer_permission,
            timeout_seconds=agent_timeout_seconds,
        )

        round_summaries.append(
            collect_round_metadata(
                round_number=round_number,
                build_report=build_report,
                builder_profile=args.builder,
                builder_permission=final_builder_permission,
                reviewer_profile=args.reviewer,
                reviewer_permission=final_reviewer_permission,
                review_report=last_review,
            )
        )

        approved = bool(last_review.get("approved"))
        blockers = int(last_review.get("blocker_count", 0))
        next_action = last_review.get("next_action")

        if approved or next_action == "approve":
            break

        if round_number == max_rounds:
            break

        review_findings = json.dumps(last_review, indent=2)
        if blockers == 0 and next_action != "revise":
            break

    final_blocker_count = int(last_review.get("blocker_count", 0)) if last_review else 0
    loop_exhausted_with_blockers = (
        rounds_completed >= max_rounds
        and final_blocker_count > 0
        and not bool(last_review and last_review.get("approved"))
    )

    final_summary = build_markdown_summary(
        repo=base_repo,
        repo_for_run=repo_for_run,
        artifact_dir=artifact_dir,
        baseline=baseline,
        worktree_branch=worktree_branch,
        status_short=final_status_short,
        builder=args.builder,
        reviewer=args.reviewer,
        builder_permission=final_builder_permission,
        reviewer_permission=final_reviewer_permission,
        create_worktree_enabled=args.create_worktree,
        final_review=last_review,
        rounds=round_summaries,
        max_rounds=max_rounds,
        rounds_completed=rounds_completed,
        loop_exhausted_with_blockers=loop_exhausted_with_blockers,
    )
    write_text(artifact_dir / "final-summary.md", final_summary)

    summary = {
        "repo": str(base_repo),
        "repo_for_run": str(repo_for_run),
        "baseline": baseline,
        "builder": args.builder,
        "reviewer": args.reviewer,
        "builder_permission": final_builder_permission,
        "reviewer_permission": final_reviewer_permission,
        "agent_timeout_seconds": agent_timeout_seconds,
        "worktree_branch": worktree_branch,
        "rounds_completed": rounds_completed,
        "max_rounds": max_rounds,
        "loop_exhausted_with_blockers": loop_exhausted_with_blockers,
        "artifact_dir": str(artifact_dir),
        "final_summary_path": str(artifact_dir / "final-summary.md"),
        "final_review": last_review,
    }

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
