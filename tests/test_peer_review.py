import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "peer_review.py"


def load_peer_review_module():
    spec = importlib.util.spec_from_file_location("peer_review", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PeerReviewHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_peer_review_module()

    def test_extract_json_skips_non_json_braces(self):
        raw = textwrap.dedent(
            """
            note {not json}
            {"approved": true, "summary": "ok", "blocker_count": 0, "findings": [], "test_gaps": [], "next_action": "approve"}
            trailing {text}
            """
        ).strip()

        payload = self.module.extract_json(raw)

        self.assertTrue(payload["approved"])
        self.assertEqual(payload["summary"], "ok")

    def test_build_run_id_adds_random_suffix(self):
        with mock.patch.object(self.module.secrets, "token_hex", side_effect=["abc123", "def456"]):
            first = self.module.build_run_id("20260416-220000", "task")
            second = self.module.build_run_id("20260416-220000", "task")

        self.assertEqual(first, "20260416-220000-task-abc123")
        self.assertEqual(second, "20260416-220000-task-def456")
        self.assertNotEqual(first, second)

    def test_build_worktree_plan_uses_run_id(self):
        worktree_path, branch = self.module.build_worktree_plan(
            Path("/tmp/example-repo"),
            run_id="20260416-220000-task-abc123",
            requested_root=None,
        )

        self.assertEqual(worktree_path, Path("/tmp/example-repo/.peer-review-worktrees/20260416-220000-task-abc123"))
        self.assertEqual(branch, "peer-review/20260416-220000-task-abc123")

    def test_build_command_accepts_distinct_builder_and_reviewer_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            schema = repo / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")

            profiles = {
                "builder": {
                    "command": ["builder", "{repo}", "{schema_path}", "-"],
                    "permission_profiles": {
                        "workspace_write": ["--builder-write"],
                        "read_only": ["--builder-read"],
                    },
                    "default_permission": "workspace_write",
                },
                "reviewer": {
                    "command": ["reviewer", "{repo}", "{schema_path}", "-"],
                    "permission_profiles": {
                        "read_only": ["--reviewer-read"],
                        "workspace_write": ["--reviewer-write"],
                    },
                    "default_permission": "read_only",
                },
            }

            builder_command, builder_permission = self.module.build_command(
                profile_name="builder",
                profiles=profiles,
                repo=repo,
                schema_path=schema,
                permission_name="workspace_write",
            )
            reviewer_command, reviewer_permission = self.module.build_command(
                profile_name="reviewer",
                profiles=profiles,
                repo=repo,
                schema_path=schema,
                permission_name="read_only",
            )

        self.assertEqual(builder_permission, "workspace_write")
        self.assertEqual(reviewer_permission, "read_only")
        self.assertIn("--builder-write", builder_command)
        self.assertIn("--reviewer-read", reviewer_command)


class PeerReviewCliTest(unittest.TestCase):
    def run_script(self, *args: str, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            cwd=str(cwd or REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

    def init_git_repo(self, repo: Path) -> None:
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True)
        (repo / "README.md").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)

    def write_task(self, path: Path) -> None:
        path.write_text("# Task\n\n## Objective\n- Test\n", encoding="utf-8")

    def test_dry_run_roots_artifacts_under_base_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            self.init_git_repo(repo)
            task = repo / "task.md"
            self.write_task(task)

            result = self.run_script(
                "--repo",
                str(repo),
                "--task",
                str(task),
                "--builder",
                "codex-builder",
                "--reviewer",
                "claude-reviewer",
                "--create-worktree",
                "--dry-run",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            artifact_dir = Path(payload["artifact_dir"]).resolve()
            expected_root = (repo.resolve() / ".peer-review" / "runs")
            worktree_root = (repo.resolve() / ".peer-review-worktrees")

            self.assertTrue(artifact_dir.is_relative_to(expected_root))
            self.assertTrue(Path(payload["repo_for_run"]).resolve().is_relative_to(worktree_root))

    def test_rounds_must_be_at_least_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            self.init_git_repo(repo)
            task = repo / "task.md"
            self.write_task(task)

            result = self.run_script(
                "--repo",
                str(repo),
                "--task",
                str(task),
                "--builder",
                "codex-builder",
                "--reviewer",
                "codex-reviewer",
                "--rounds",
                "0",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--rounds must be at least 1", result.stderr)

    def test_agent_timeout_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            self.init_git_repo(repo)
            task = repo / "task.md"
            self.write_task(task)
            slow_agent = repo / "slow_agent.py"
            slow_agent.write_text(
                textwrap.dedent(
                    """
                    import sys
                    import time

                    time.sleep(2)
                    sys.stdout.write("{}")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            config = repo / "agents.json"
            config.write_text(
                json.dumps(
                    {
                        "default_rounds": 2,
                        "default_agent_timeout_seconds": 1,
                        "profiles": {
                            "slow-builder": {
                                "role": "builder",
                                "vendor": "test",
                                "command": [sys.executable, str(slow_agent)],
                                "permission_profiles": {"default": []},
                                "default_permission": "default",
                            },
                            "slow-reviewer": {
                                "role": "reviewer",
                                "vendor": "test",
                                "command": [sys.executable, str(slow_agent)],
                                "permission_profiles": {"default": []},
                                "default_permission": "default",
                            },
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_script(
                "--repo",
                str(repo),
                "--task",
                str(task),
                "--builder",
                "slow-builder",
                "--reviewer",
                "slow-reviewer",
                "--builder-permission",
                "default",
                "--reviewer-permission",
                "default",
                "--config",
                str(config),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("timed out after 1 seconds", result.stderr.lower())
            artifact_root = repo / ".peer-review" / "runs"
            run_dirs = [path for path in artifact_root.iterdir() if path.is_dir()]
            self.assertEqual(len(run_dirs), 1)
            stderr_path = run_dirs[0] / "round-1.builder.stderr.txt"
            self.assertTrue(stderr_path.exists())
            self.assertIn("Timed out after 1 seconds.", stderr_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
