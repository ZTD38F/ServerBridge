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
    # Absolute line positions of the first retained item in each ring buffer.
    stdout_base:int=0
    stderr_base:int=0
    out_cursor:int=0
    err_cursor:int=0
    lock:threading.Lock=field(default_factory=threading.Lock)

_sessions:dict[str,Session]={}
_guard=threading.Lock()

def _pump(s:Session, stream, channel:str) -> None:
    buf=s.stdout if channel=='stdout' else s.stderr
    base_attr='stdout_base' if channel=='stdout' else 'stderr_base'
    try:
        for line in iter(stream.readline,''):
            with s.lock:
                if len(buf)==buf.maxlen:
                    setattr(s,base_attr,getattr(s,base_attr)+1)
                buf.append(line.rstrip('\n'))
    finally:
        stream.close()

def start(argv:list[str],cwd:str,env:dict[str,str]) -> dict[str,Any]:
    # Admission and registration must be one critical section. Otherwise two
    # concurrent callers can both see a free slot before either starts a child.
    with _guard:
        live=sum(s.proc.poll() is None for s in _sessions.values())
        if live>=MAX_SESSIONS:
            raise RuntimeError('SESSION_LIMIT')
        proc=subprocess.Popen(argv,cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,bufsize=1,env=env,start_new_session=True,close_fds=True)
        sid=uuid.uuid4().hex
        s=Session(sid,proc,argv,cwd)
        _sessions[sid]=s
    threading.Thread(target=_pump,args=(s,proc.stdout,'stdout'),daemon=True).start()
    threading.Thread(target=_pump,args=(s,proc.stderr,'stderr'),daemon=True).start()
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
        out_start=max(s.out_cursor,s.stdout_base)
        err_start=max(s.err_cursor,s.stderr_base)
        dropped_out=max(0,s.stdout_base-s.out_cursor)
        dropped_err=max(0,s.stderr_base-s.err_cursor)
        out=list(s.stdout)[out_start-s.stdout_base:out_start-s.stdout_base+max_lines]
        err=list(s.stderr)[err_start-s.stderr_base:err_start-s.stderr_base+max_lines]
        s.out_cursor=out_start+len(out)
        s.err_cursor=err_start+len(err)
        out_more=s.out_cursor < s.stdout_base+len(s.stdout)
        err_more=s.err_cursor < s.stderr_base+len(s.stderr)
    result=info(s)
    result.update({'stdout':'\n'.join(out),'stderr':'\n'.join(err),
        'stdout_has_more':out_more,'stderr_has_more':err_more,
        'stdout_dropped_lines':dropped_out,'stderr_dropped_lines':dropped_err})
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
