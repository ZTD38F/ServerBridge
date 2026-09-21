from __future__ import annotations

import re
from pathlib import Path

text = Path("install.sh").read_text(encoding="utf-8")

start_marker = "cat > /usr/local/sbin/serverbridgectl <<EOF"
start = text.index(start_marker) + len(start_marker)
end = text.index("\nEOF\n  chmod 755 /usr/local/sbin/serverbridgectl", start)
template = text[start:end]

problems: list[str] = []

# Positional arguments belong to generated serverbridgectl, not install.sh.
if re.search(r"(?<!\\\\)\\$\\{[12](?::-[^}]*)?\\}", template):
    problems.append("unescaped positional parameter in serverbridgectl template")

# Command substitutions must survive installer rendering too.
if re.search(r"(?<!\\\\)\\$\\(", template):
    problems.append("unescaped command substitution in serverbridgectl template")

assert not problems, "; ".join(problems)

assert 'case "\\${1:-check}" in' in template
assert 'log="\\$(mktemp /tmp/serverbridge-doctor.XXXXXX)"' in template
assert '"\\${2:-100}"' in template

print("installer template expansion test passed")
