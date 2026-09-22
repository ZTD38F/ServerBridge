from __future__ import annotations

from pathlib import Path

text = Path("install.sh").read_text(encoding="utf-8")

start_marker = "cat > /usr/local/sbin/serverbridgectl <<EOF"
start = text.index(start_marker) + len(start_marker)
end = text.index("\nEOF\n  chmod 755 /usr/local/sbin/serverbridgectl", start)
template = text[start:end]

problems: list[str] = []

for number in ("1", "2"):
    raw = "${" + number
    escaped = "\\${" + number
    if raw in template.replace(escaped, ""):
        problems.append(f"unescaped positional parameter ${number} in generated CLI")

# Every command substitution inside this heredoc belongs to the generated CLI.
if "$(" in template.replace("\\$(", ""):
    problems.append("unescaped command substitution in generated CLI")

assert not problems, "; ".join(problems)

assert 'case "\\${1:-check}" in' in template
assert 'log="\\$(mktemp /tmp/serverbridge-doctor.XXXXXX)"' in template
assert '"\\${2:-100}"' in template
assert "  update)" in template
assert 'tmp="\\$(mktemp /tmp/serverbridge-update.XXXXXX.sh)"' in template
assert 'bash "\\$tmp" "\\$@" || rc=\\$?' in template

print("installer template expansion test passed")
