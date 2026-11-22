"""Offline fail-closed contracts for GitHub Actions release workflows."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeliveryWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ci = (ROOT / ".github/workflows/ci.yml").read_text()
        cls.release = (ROOT / ".github/workflows/release.yml").read_text()
        cls.proposal = (ROOT / ".github/workflows/release-proposal.yml").read_text()

    def test_release_requires_successful_main_ci(self):
        for value in ("workflow_run:", "conclusion == 'success'",
                      "workflow_run.event == 'push'", "head_branch == 'main'",
                      "head_repository.full_name == github.repository",
                      'SOURCE_SHA="$(git rev-parse HEAD)"',
                      'LIVE_SHA="$(gh api', '"$SOURCE_SHA" != "$LIVE_SHA"',
                      "gh run list --workflow ci.yml"):
            with self.subTest(value=value):
                self.assertIn(value, self.release)

    def test_release_uses_exact_checkout_and_fleet_gate(self):
        self.assertIn('ref: $', self.release)
        self.assertIn("--target ", self.release)
        self.assertIn("steps.source.outputs.sha", self.release)
        self.assertIn("gh issue view 29 --json state", self.release)
        self.assertIn("steps.fleet.outputs.ready == 'true'", self.release)
        self.assertIn("Stable release held", self.release)
        self.assertNotIn("paths:\n      - pyproject.toml", self.release)

    def test_proposal_cannot_publish_or_merge(self):
        for value in ("workflow_run:", "conclusion == 'success'",
                      "head_branch == 'main'", "SOURCE_SHA", "LIVE_SHA",
                      "gh pr create --draft", "gh workflow run ci.yml --ref",
                      "gh pr list --state open"):
            with self.subTest(value=value):
                self.assertIn(value, self.proposal)
        for denied in ("gh pr merge", "gh release create", "systemctl"):
            self.assertNotIn(denied, self.proposal)

    def test_ci_rechecks_release_planner_and_can_dispatch(self):
        self.assertIn("workflow_dispatch:", self.ci)
        self.assertIn("test_release_train.py", self.ci)
        self.assertIn("test_release_workflow_contract.py", self.ci)


if __name__ == "__main__":
    unittest.main()
