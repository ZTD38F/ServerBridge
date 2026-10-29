from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from serverbridge.core import _redact_obj, audit

MARKER = "synthetic_marker_no_real_secret_0332"

class AuditRedactionTests(unittest.TestCase):
    def test_nested_sensitive_keys(self) -> None:
        data = {"api_key": MARKER, "details": [
            {"client_secret": MARKER, "access-token": MARKER},
            {"request": {"authorization": MARKER}},
        ]}
        output = json.dumps(_redact_obj(data))
        self.assertNotIn(MARKER, output)
        self.assertGreaterEqual(output.count("[REDACTED]"), 4)

    def test_ordinary_metrics_still_visible(self) -> None:
        data = {"token_count": 12, "api_key_count": 4, "status": "ok"}
        self.assertEqual(_redact_obj(data), data)

    def test_nested_audit_sink(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            before = os.environ.get("SERVERBRIDGE_AUDIT_LOG")
            os.environ["SERVERBRIDGE_AUDIT_LOG"] = str(Path(d) / "audit.jsonl")
            try:
                audit("test", "fixture", "ok", {
                    "api_key": MARKER, "nested": {"access_token": MARKER}
                })
                content = (Path(d) / "audit.jsonl").read_text()
                self.assertNotIn(MARKER, content)
                self.assertIn("[REDACTED]", content)
            finally:
                if before is None:
                    os.environ.pop("SERVERBRIDGE_AUDIT_LOG", None)
                else:
                    os.environ["SERVERBRIDGE_AUDIT_LOG"] = before

if __name__ == "__main__":
    unittest.main()
