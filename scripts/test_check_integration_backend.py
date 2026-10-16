"""A cached check must have intact evidence for the exact candidate/container."""

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-integration-backend.py")
SPEC = importlib.util.spec_from_file_location("integration_runner", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        workspace = SCRIPT.parent.parent.resolve()
        cache_root = workspace / ".pytest_cache"
        cache_root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=cache_root)
        self.path = Path(self.directory.name).resolve()
        self.assertTrue(self.path.is_relative_to(workspace))
        self.addCleanup(self.directory.cleanup)
        original = runner.CACHE
        runner.CACHE = self.path
        self.addCleanup(setattr, runner, "CACHE", original)
        self.selector = "chatballs/conversations/test_transfer_api.py"
        self.output = b"1 passed"
        self.report = {
            "key": {"candidate": "unit-sha", "container": "unit-container", "selectors": [self.selector]},
            "exit_code": 0,
            "output_sha256": hashlib.sha256(self.output).hexdigest(),
            "completed_at": "unit-test",
        }

    def write(self):
        (self.path / "report.json").write_text(json.dumps(self.report), encoding="utf-8")
        (self.path / "report.log").write_bytes(self.output)

    def covered(self, candidate="unit-sha", container="unit-container"):
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.successful_selectors(candidate, container)

    def test_intact_success_covers_only_its_recorded_selectors(self):
        self.write()
        self.assertEqual(self.covered(), {self.selector})

    def test_another_candidate_or_container_cannot_reuse_evidence(self):
        self.write()
        self.assertEqual(self.covered(candidate="other-sha"), set())
        self.assertEqual(self.covered(container="other-container"), set())

    def test_failure_or_modified_output_is_not_evidence(self):
        self.report["exit_code"] = 1
        self.write()
        self.assertEqual(self.covered(), set())
        self.report["exit_code"] = 0
        self.write()
        (self.path / "report.log").write_bytes(b"failed")
        self.assertEqual(self.covered(), set())

    def test_missing_output_or_corrupt_report_is_not_evidence(self):
        self.write()
        (self.path / "report.log").unlink()
        self.assertEqual(self.covered(), set())
        (self.path / "report.json").write_text("broken", encoding="utf-8")
        self.assertEqual(self.covered(), set())
