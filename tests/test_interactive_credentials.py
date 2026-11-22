from __future__ import annotations
import os, subprocess
from pathlib import Path

SOURCE=Path("install.sh").read_text()
assert SOURCE.index("RUNTIME_KEY=") < SOURCE.index("TUNNEL_ID_EXPLICIT=0"), "Read credentials before deriving explicit flags"
FUNCTION="prompt_credentials() {"+SOURCE.split("prompt_credentials() {",1)[1].split("\nselect_access_mode() {",1)[0]
INTERACTIVE=FUNCTION.replace('if ((DRY_RUN)) || [[ ! -r /dev/tty ]] || [[ ! -t 2 ]]; then','if ((DRY_RUN)) || false; then')

def check(stored_id="",stored_key="",choice_id="",choice_key="",new_id="",new_key="",explicit_id=False,explicit_key=False,interactive=True,expect_id=None,expect_key=None,fail=False):
    e=os.environ.copy()
    e.update(dict(STORED_ID=stored_id,STORED_KEY=stored_key,CHOICE_ID=choice_id,CHOICE_KEY=choice_key,NEW_ID=new_id,NEW_KEY=new_key,EXPECT_ID=stored_id if expect_id is None else expect_id,EXPECT_KEY=stored_key if expect_key is None else expect_key,EXPLICIT_ID=str(int(explicit_id)),EXPLICIT_KEY=str(int(explicit_key))))
    head='''set -Eeuo pipefail
TUNNEL_ID="$STORED_ID"; RUNTIME_KEY="$STORED_KEY"
TUNNEL_ID_EXPLICIT="$EXPLICIT_ID"; RUNTIME_KEY_EXPLICIT="$EXPLICIT_KEY"
DRY_RUN=0; RESET=""; BOLD=""; DIM=""; BLUE=""
say() { :; }; info() { :; }; ok() { :; }; die() { echo INVALID >&2; exit 3; }
visible_input() {
  case "$1" in
    "Reuse previously saved Tunnel ID? "*) printf '%s' "$CHOICE_ID" ;;
    "New Tunnel ID: "*) printf '%s' "$NEW_ID" ;;
    "Reuse previously saved runtime API key? "*) printf '%s' "$CHOICE_KEY" ;;
    *) exit 9 ;;
  esac
}
secret_input() { [[ "$1" == "New runtime API key: " ]] || exit 10; printf '%s' "$NEW_KEY"; }
'''
    tail='''prompt_credentials
[[ "$TUNNEL_ID" == "$EXPECT_ID" ]]
[[ "$RUNTIME_KEY" == "$EXPECT_KEY" ]]
printf 'PASS'
'''
    result=subprocess.run(["bash","-c",head+(INTERACTIVE if interactive else FUNCTION)+"\n"+tail],env=e,capture_output=True,text=True,timeout=10)
    if fail: assert result.returncode!=0
    else:
        assert result.returncode==0,(result.returncode,result.stderr)
        assert result.stdout=="PASS"
        assert "sk-test" not in result.stderr

def test_empty_enter_reuses_both(): check(stored_id="tunnel_existing1234",stored_key="sk-test-original")
def test_change_id_keep_key(): check(stored_id="tunnel_existing1234",stored_key="sk-test-original",choice_id="n",new_id="tunnel_new98765",expect_id="tunnel_new98765")
def test_change_key_keep_id(): check(stored_id="tunnel_existing1234",stored_key="sk-test-original",choice_key="no",new_key="sk-test-replacement",expect_key="sk-test-replacement")
def test_fresh_install(): check(new_id="tunnel_new98765",new_key="sk-test-new",expect_id="tunnel_new98765",expect_key="sk-test-new")
def test_explicit_override(): check(stored_id="tunnel_explicit9999",stored_key="sk-test-explicit",choice_id="no",choice_key="no",explicit_id=True,explicit_key=True)
def test_no_tty_reuses_saved(): check(stored_id="tunnel_existing1234",stored_key="sk-test-original",interactive=False)
def test_no_tty_no_credentials_fails(): check(interactive=False,fail=True)
def test_invalid_choice_fails(): check(stored_id="tunnel_existing1234",stored_key="sk-test-original",choice_id="perhaps",fail=True)
def test_russian_answers(): check(stored_id="tunnel_existing1234",stored_key="sk-test-original",choice_id="Нет",new_id="tunnel_new98765",choice_key="Да",expect_id="tunnel_new98765")

if __name__=="__main__":
    for name,f in sorted(globals().items()):
        if name.startswith("test_") and callable(f): f()
    print("Interactive credential prompts passed")
