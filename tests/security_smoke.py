from __future__ import annotations
import os, subprocess, sys, tempfile
from pathlib import Path
from serverbridge.core import resolve_existing, resolve_write, redact

def main():
    old_allowed=os.environ.get('SERVERBRIDGE_ALLOWED_ROOTS'); old_protected=os.environ.get('SERVERBRIDGE_PROTECTED_PATHS')
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); safe=root/'safe.txt'; secrets=root/'secrets'; secret=secrets/'runtime.env'
            secrets.mkdir(); safe.write_text('safe'); secret.write_text('secret')
            os.environ['SERVERBRIDGE_ALLOWED_ROOTS']=str(root); os.environ['SERVERBRIDGE_PROTECTED_PATHS']=str(secrets)
            assert resolve_existing(str(safe))==safe.resolve()
            assert resolve_write(str(root/'new.txt'))==(root/'new.txt').resolve()
            try: resolve_existing(str(secret))
            except PermissionError: pass
            else: raise AssertionError('protected path readable')
            try: resolve_write(str(secrets/'new.txt'))
            except PermissionError: pass
            else: raise AssertionError('protected path writable')
            assert 'REDACTED' in redact('Authorization: Bearer abcdefghijklmnop')
        env=os.environ.copy()
        for k in ['SERVERBRIDGE_ENABLE_EXEC','SERVERBRIDGE_ENABLE_WRITE','SERVERBRIDGE_ENABLE_PROCESS','SERVERBRIDGE_ENABLE_SERVICE_CONTROL']: env.pop(k,None)
        probe='''import asyncio\nfrom mcp import Client\nfrom serverbridge.server import mcp\nasync def x():\n async with Client(mcp,raise_exceptions=True) as c:\n  n={t.name for t in (await c.list_tools()).tools}\n  assert "run_command" not in n and "write_file" not in n and "start_process" not in n and "service_restart" not in n\nasyncio.run(x())'''
        subprocess.run([sys.executable,'-c',probe],env=env,check=True)
    finally:
        if old_allowed is None: os.environ.pop('SERVERBRIDGE_ALLOWED_ROOTS',None)
        else: os.environ['SERVERBRIDGE_ALLOWED_ROOTS']=old_allowed
        if old_protected is None: os.environ.pop('SERVERBRIDGE_PROTECTED_PATHS',None)
        else: os.environ['SERVERBRIDGE_PROTECTED_PATHS']=old_protected
if __name__=='__main__': main(); print('security boundary smoke test passed')
