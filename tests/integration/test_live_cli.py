import importlib.util
import json
import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "peer_review.py"
RUN_LIVE = os.environ.get("CI_HAS_CLI_AGENTS") == "1"


def load_peer_review_module():
    spec = importlib.util.spec_from_file_location("peer_review", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def ensure_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


@unittest.skipUnless(RUN_LIVE, "Set CI_HAS_CLI_AGENTS=1 to run live CLI integration checks.")
class LiveCliIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_peer_review_module()

    def test_claude_json_schema_returns_envelope_with_extractable_structured_output(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["approved", "summary", "blocker_count", "findings", "test_gaps", "next_action"],
            "properties": {
                "approved": {"type": "boolean"},
                "summary": {"type": "string"},
                "blocker_count": {"type": "integer", "minimum": 0},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["severity", "title", "detail"],
                        "properties": {
                            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                            "title": {"type": "string"},
                            "detail": {"type": "string"},
                        },
                    },
                },
                "test_gaps": {"type": "array", "items": {"type": "string"}},
                "next_action": {"type": "string", "enum": ["approve", "revise", "escalate_to_human"]},
            },
        }
        cmd = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
            "Return approved=true, summary='hi', blocker_count=0, findings=[], test_gaps=[], next_action='approve' as structured output only.",
        ]

        result = subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        envelope = self.module.extract_json(result.stdout)
        payload = self.module.extract_profile_payload(envelope, {"output_extract_path": ["structured_output"]})

        self.assertIn("structured_output", envelope)
        self.assertTrue(payload["approved"])
        self.assertEqual(payload["summary"], "hi")

    def test_codex_accepts_review_schema(self):
        cmd = [
            "codex",
            "exec",
            "-C",
            str(REPO_ROOT),
            "--add-dir",
            str(REPO_ROOT),
            "--output-schema",
            str(REPO_ROOT / "schemas" / "review-report.schema.json"),
            "-",
        ]
        prompt = "Return a valid review report JSON only. Use null for file, line, and suggested_fix when not applicable."

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=20,
            )
            combined = f"{result.stdout}\n{result.stderr}"
            self.assertNotIn("invalid_json_schema", combined)
            self.assertNotIn('"code": "invalid_json_schema"', combined)
        except subprocess.TimeoutExpired as exc:
            partial = (ensure_text(exc.stdout) + "\n" + ensure_text(exc.stderr)).lower()
            self.assertNotIn("invalid_json_schema", partial)


if __name__ == "__main__":
    unittest.main()
