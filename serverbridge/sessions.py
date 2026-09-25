from __future__ import annotations
import os, signal, subprocess, threading, time, uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

MAX_LINES=max(100,int(os.getenv('SERVERBRIDGE_SESSION_MAX_LINES','5000')))
MAX_SESSIONS=max(1,int(os.getenv('SERVERBRIDGE_MAX_SESSIONS','16')))

@dataclass
class Session:
    id:str
    proc:subprocess.Popen[str]
    argv:list[str]
    cwd:str
    started:float=field(default_factory=time.time)
    stdout:deque[str]=field(default_factory=lambda:deque(maxlen=MAX_LINES))
    stderr:deque[str]=field(default_factory=lambda:deque(maxlen=MAX_LINES))
    out_cursor:int=0
    err_cursor:int=0
    lock:threading.Lock=field(default_factory=threading.Lock)

_sessions:dict[str,Session]={}
_guard=threading.Lock()

def _pump(stream, buf:deque[str]) -> None:
    try:
        for line in iter(stream.readline,''):
            buf.append(line.rstrip('\n'))
    finally:
        stream.close()

def start(argv:list[str],cwd:str,env:dict[str,str]) -> dict[str,Any]:
    with _guard:
        live=[s for s in _sessions.values() if s.proc.poll() is None]
        if len(live)>=MAX_SESSIONS:
            raise RuntimeError('SESSION_LIMIT')
    proc=subprocess.Popen(argv,cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,bufsize=1,env=env,start_new_session=True,close_fds=True)
    sid=uuid.uuid4().hex
    s=Session(sid,proc,argv,cwd)
    with _guard: _sessions[sid]=s
    threading.Thread(target=_pump,args=(proc.stdout,s.stdout),daemon=True).start()
    threading.Thread(target=_pump,args=(proc.stderr,s.stderr),daemon=True).start()
    return info(s)

def get(sid:str)->Session:
    try:return _sessions[sid]
    except KeyError:raise KeyError('PROCESS_SESSION_NOT_FOUND')

def info(s:Session)->dict[str,Any]:
    code=s.proc.poll()
    return {'session_id':s.id,'pid':s.proc.pid,'argv0':s.argv[0],'argument_count':len(s.argv),'cwd':s.cwd,
        'started_at':int(s.started),'running':code is None,'exit_code':code}

def list_all()->list[dict[str,Any]]:
    with _guard:return [info(s) for s in _sessions.values()]

def read(sid:str,max_lines:int=200)->dict[str,Any]:
    s=get(sid); max_lines=max(1,min(int(max_lines),2000))
    with s.lock:
        out=list(s.stdout); err=list(s.stderr)
        new_out=out[s.out_cursor:s.out_cursor+max_lines]
        new_err=err[s.err_cursor:s.err_cursor+max_lines]
        s.out_cursor=min(len(out),s.out_cursor+len(new_out))
        s.err_cursor=min(len(err),s.err_cursor+len(new_err))
    result=info(s)
    result.update({'stdout':'\n'.join(new_out),'stderr':'\n'.join(new_err),
        'stdout_has_more':s.out_cursor<len(out),'stderr_has_more':s.err_cursor<len(err)})
    return result

def send(sid:str,data:str)->dict[str,Any]:
    s=get(sid)
    if s.proc.poll() is not None: raise RuntimeError('PROCESS_EXITED')
    assert s.proc.stdin is not None
    s.proc.stdin.write(data); s.proc.stdin.flush()
    return info(s)

def terminate(sid:str,force:bool=False)->dict[str,Any]:
    s=get(sid)
    if s.proc.poll() is None:
        try: os.killpg(s.proc.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError: pass
        try:s.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(s.proc.pid,signal.SIGKILL); s.proc.wait(timeout=3)
    return info(s)
