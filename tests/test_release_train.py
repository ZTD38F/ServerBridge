"""Offline regression tests for release proposal and fail-closed checks."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ENTRY = Path(__file__).resolve().parents[1] / "scripts/release_train.py"
spec = importlib.util.spec_from_file_location("release_train_under_test", ENTRY)
assert spec and spec.loader
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)
SHA = "a" * 40


class ReleaseTrainTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        (self.path / "serverbridge").mkdir()
        (self.path / "pyproject.toml").write_text('[project]\nversion = "0.5.16"\n')
        (self.path / "plugin.json").write_text('{\n  "version": "0.5.16",\n}\n')
        (self.path / "serverbridge/__init__.py").write_text('__version__ = "0.5.16"\n')
        (self.path / "CHANGELOG.md").write_text(
            "# Changelog\n\n## Unreleased\n\n- Fix a real-time stream.\n\n## 0.5.16\n"
        )

    def test_patch_and_readback(self):
        p = train.plan(self.path, "v0.5.16", SHA)
        self.assertEqual(p["branch"], "automated-release/v0.5.17")
        self.assertEqual(len(train.apply(self.path, p, "2026-11-23")), 4)
        self.assertEqual(train.sources(self.path)[0], "0.5.17")
        self.assertIn("## 0.5.17 — 2026-11-23",
                      (self.path / "CHANGELOG.md").read_text())
        self.assertIn("Fix a real-time stream",
                      (self.path / "CHANGELOG.md").read_text())

    def test_no_duplicate_when_release_pending(self):
        p = train.plan(self.path, "v0.5.16", SHA)
        train.apply(self.path, p, "2026-11-23")
        self.assertEqual(train.plan(self.path, "v0.5.16", SHA)["action"],
                         "await_release")

    def test_without_unreleased_notes(self):
        (self.path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.5.16\n")
        train.apply(self.path, train.plan(self.path, "v0.5.16", SHA), "2026-11-23")
        self.assertIn(SHA[:12], (self.path / "CHANGELOG.md").read_text())

    def test_published_newer_than_code_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "older"):
            train.plan(self.path, "v0.5.17", SHA)

    def test_divergent_package_and_manifest_fails_closed(self):
        (self.path / "plugin.json").write_text('{\n  "version": "0.5.17",\n}\n')
        with self.assertRaisesRegex(ValueError, "mismatch"):
            train.plan(self.path, "v0.5.16", SHA)

    def test_invalid_sha(self):
        for sha in ["abc", "A"*40, "g"*40, "../" + "a"*36]:
            with self.subTest(sha=sha):
                with self.assertRaises(ValueError):
                    train.plan(self.path, "v0.5.16", sha)

    def test_invalid_semver(self):
        for tag in ["v1.2", "v01.2.3", "v1.2.3-rc1", "latest"]:
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    train.plan(self.path, tag, SHA)

    def test_invalid_date_does_not_mutate_files(self):
        p = train.plan(self.path, "v0.5.16", SHA)
        before = {str(f.relative_to(self.path)): f.read_bytes()
                  for f in self.path.rglob("*") if f.is_file()}
        with self.assertRaises(ValueError):
            train.apply(self.path, p, "not-a-date")
        after = {str(f.relative_to(self.path)): f.read_bytes()
                 for f in self.path.rglob("*") if f.is_file()}
        self.assertEqual(before, after)

    def test_reject_unrecognized_changelog_format(self):
        (self.path / "CHANGELOG.md").write_text("Bogus changelog")
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            train.apply(self.path, train.plan(self.path, "v0.5.16", SHA), "2026-11-23")

    def test_current_repository_consistency(self):
        root = ENTRY.parents[1]
        version, _ = train.sources(root)
        self.assertTrue(train.semver(version))


if __name__ == "__main__":
    unittest.main()
