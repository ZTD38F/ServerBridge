from __future__ import annotations

import os
import tempfile
from pathlib import Path

from serverbridge.server import _resolve_allowed


def main() -> None:
    old_allowed = os.environ.get("SERVERBRIDGE_ALLOWED_ROOTS")
    old_protected = os.environ.get("SERVERBRIDGE_PROTECTED_PATHS")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / "safe.txt"
            secret_dir = root / "secrets"
            secret = secret_dir / "runtime.env"

            secret_dir.mkdir()
            safe.write_text("safe", encoding="utf-8")
            secret.write_text("secret", encoding="utf-8")

            os.environ["SERVERBRIDGE_ALLOWED_ROOTS"] = str(root)
            os.environ["SERVERBRIDGE_PROTECTED_PATHS"] = str(secret_dir)

            assert _resolve_allowed(str(safe)) == safe.resolve()

            try:
                _resolve_allowed(str(secret))
            except PermissionError:
                pass
            else:
                raise AssertionError("protected path was readable")
    finally:
        if old_allowed is None:
            os.environ.pop("SERVERBRIDGE_ALLOWED_ROOTS", None)
        else:
            os.environ["SERVERBRIDGE_ALLOWED_ROOTS"] = old_allowed

        if old_protected is None:
            os.environ.pop("SERVERBRIDGE_PROTECTED_PATHS", None)
        else:
            os.environ["SERVERBRIDGE_PROTECTED_PATHS"] = old_protected


if __name__ == "__main__":
    main()
    print("security boundary smoke test passed")
