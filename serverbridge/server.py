from __future__ import annotations
import fnmatch, itertools, os, platform, pwd, re, shutil, socket, subprocess, tempfile, time, urllib.request
from collections import deque
from pathlib import Path
from typing import Any
from mcp.server import MCPServer

from . import __version__
from .core import (
    EXEC_ENABLED, WRITE_ENABLED, PROCESS_ENABLED, SERVICE_CONTROL_ENABLED,
    MAX_CAPTURE, allowed_roots, protected_paths, resolve_existing, resolve_write,
    sha256_file, atomic_write, audit, truncate, redact
)
from . import sessions

mcp=MCPServer('ServerBridge')
EXEC_MAX_TIMEOUT=max(1,min(int(os.getenv('SERVERBRIDGE_EXEC_MAX_TIMEOUT','900')),3600))

def _init_system()->str:
    if Path('/run/systemd/system').is_dir() and shutil.which('systemctl'): return 'systemd'
    if shutil.which('rc-service'): return 'openrc'
    return 'unknown'

def _exec_environment()->dict[str,str]:
    allowed={'PATH','HOME','LANG','LANGUAGE','LC_ALL','LC_CTYPE','TERM','TMPDIR','USER','LOGNAME','SHELL','TZ',
      'HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR',
      'REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE'}
    return {k:v for k,v in os.environ.items() if k in allowed}

def _command_argv(argv:list[str])->list[str]:
    if not isinstance(argv,list) or not argv or len(argv)>128: raise ValueError('argv must contain 1-128 arguments')
    out=[]; total=0
    for item in argv:
        if not isinstance(item,str) or not item or '\x00' in item: raise ValueError('argv contains an invalid argument')
        b=item.encode('utf-8'); total+=len(b)
        if len(b)>8192: raise ValueError('one argv item is too large')
        out.append(item)
    if total>65536: raise ValueError('argv is too large')
    return out

def _service_name(name:str)->str:
    allowed=set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@_.:-')
    if not name or len(name)>200 or any(ch not in allowed for ch in name): raise ValueError('Invalid service name')
    return name

@mcp.tool()
def server_info()->dict[str,Any]:
    usage=shutil.disk_usage('/')
    try: uptime=float(Path('/proc/uptime').read_text().split()[0])
    except Exception: uptime=None
    return {'serverbridge_version':__version__,'hostname':socket.gethostname(),'platform':platform.platform(),
      'kernel':platform.release(),'architecture':platform.machine(),'python':platform.python_version(),
      'init_system':_init_system(),'cwd':os.getcwd(),'uptime_seconds':uptime,
      'disk_root':{'total':usage.total,'used':usage.used,'free':usage.free},
      'allowed_roots':[str(p) for p in allowed_roots()],
      'capabilities':{'exec':EXEC_ENABLED,'write':WRITE_ENABLED,'process':PROCESS_ENABLED,'service_control':SERVICE_CONTROL_ENABLED}}

@mcp.tool()
def file_stat(path:str)->dict[str,Any]:
    p=resolve_existing(path); st=p.lstat()
    kind='symlink' if p.is_symlink() else 'dir' if p.is_dir() else 'file' if p.is_file() else 'other'
    return {'path':str(p),'type':kind,'size':st.st_size,'mode':oct(st.st_mode & 0o7777),'uid':st.st_uid,'gid':st.st_gid,
      'mtime':int(st.st_mtime),'sha256':sha256_file(p) if p.is_file() else None}

@mcp.tool()
def list_files(path:str='.',limit:int=200,include_hidden:bool=True)->dict[str,Any]:
    target=resolve_existing(path)
    if not target.is_dir(): raise NotADirectoryError(str(target))
    limit=max(1,min(int(limit),2000)); entries=[]
    with os.scandir(target) as scan:
        candidates=[e for e in scan if include_hidden or not e.name.startswith('.')]
    candidates.sort(key=lambda e:e.name.lower()); truncated=len(candidates)>limit
    for e in candidates[:limit]:
        child=target/e.name
        try:
            st=e.stat(follow_symlinks=False)
            kind='symlink' if e.is_symlink() else 'dir' if e.is_dir(follow_symlinks=False) else 'file' if e.is_file(follow_symlinks=False) else 'other'
            entries.append({'name':e.name,'path':str(child),'type':kind,'size':st.st_size,'mode':oct(st.st_mode & 0o7777),'mtime':int(st.st_mtime)})
        except OSError as exc: entries.append({'name':e.name,'path':str(child),'error':str(exc)})
    return {'path':str(target),'entries':entries,'truncated':truncated}

@mcp.tool()
def read_file(path:str,offset:int=0,length:int=1000,tail:bool=False)->dict[str,Any]:
    p=resolve_existing(path)
    if not p.is_file(): raise FileNotFoundError(str(p))
    length=max(1,min(int(length),10000))
    if tail:
        with p.open('r',encoding='utf-8',errors='replace') as f:
            selected=list(deque(f,maxlen=length))
        return {'path':str(p),'text':''.join(selected),'start_line':None,'returned_lines':len(selected),
          'next_offset':None,'truncated':False,'size':p.stat().st_size,'sha256':sha256_file(p),'tail':True}
    start=max(0,int(offset))
    with p.open('r',encoding='utf-8',errors='replace') as f:
        selected=list(itertools.islice(f,start,start+length+1))
    has_more=len(selected)>length
    selected=selected[:length]; nxt=start+len(selected)
    return {'path':str(p),'text':''.join(selected),'start_line':start,'returned_lines':len(selected),
      'next_offset':nxt if has_more else None,'truncated':has_more,'size':p.stat().st_size,'sha256':sha256_file(p),'tail':False}

@mcp.tool()
def read_text(path:str,max_bytes:int=131072)->dict[str,Any]:
    p=resolve_existing(path)
    if not p.is_file(): raise FileNotFoundError(str(p))
    cap=max(1,min(int(max_bytes),4*1024*1024)); size=p.stat().st_size
    with p.open('rb') as f:data=f.read(cap+1)
    return {'path':str(p),'text':data[:cap].decode('utf-8',errors='replace'),'truncated':len(data)>cap or size>cap,
      'size':size,'sha256':sha256_file(p),'sha256_skipped':sha256_file(p) is None}

@mcp.tool()
def search_files(root:str='.',pattern:str='*',max_results:int=200,max_depth:int=20)->dict[str,Any]:
    base=resolve_existing(root)
    if not base.is_dir(): raise NotADirectoryError(str(base))
    max_results=max(1,min(int(max_results),2000)); max_depth=max(0,min(int(max_depth),100)); results=[]
    base_depth=len(base.parts)
    for current,dirs,files in os.walk(base):
        depth=len(Path(current).parts)-base_depth
        if depth>=max_depth: dirs[:]=[]
        dirs[:]=[d for d in dirs if not any((Path(current)/d).resolve(strict=False).is_relative_to(x) for x in protected_paths())]
        for name in itertools.chain(dirs,files):
            if fnmatch.fnmatch(name,pattern):
                results.append(str(Path(current)/name))
                if len(results)>=max_results: return {'root':str(base),'results':results,'truncated':True}
    return {'root':str(base),'results':results,'truncated':False}

@mcp.tool()
def search_text(root:str,query:str,glob:str='*',regex:bool=False,case_sensitive:bool=False,max_results:int=200)->dict[str,Any]:
    base=resolve_existing(root); max_results=max(1,min(int(max_results),2000)); results=[]
    flags=0 if case_sensitive else re.IGNORECASE
    rx=re.compile(query,flags) if regex else None
    needle=query if case_sensitive else query.lower()
    files=[base] if base.is_file() else [p for p in base.rglob(glob) if p.is_file()]
    for p in files:
        try:
            rp=resolve_existing(str(p))
            if rp.stat().st_size>8*1024*1024: continue
            for num,line in enumerate(rp.open('r',encoding='utf-8',errors='replace'),1):
                matched=bool(rx.search(line)) if rx else needle in (line if case_sensitive else line.lower())
                if matched:
                    results.append({'path':str(rp),'line':num,'text':line.rstrip()[:1000]})
                    if len(results)>=max_results:return {'results':results,'truncated':True}
        except (OSError,UnicodeError,PermissionError): continue
    return {'results':results,'truncated':False}

if WRITE_ENABLED:
    @mcp.tool()
    def write_file(path:str,content:str,expected_sha256:str|None=None)->dict[str,Any]:
        p=resolve_write(path); before=sha256_file(p) if p.exists() and p.is_file() else None
        result=atomic_write(p,content.encode('utf-8'),expected_sha256); audit('write_file',str(p),details={'before_sha256':before,'after_sha256':result['sha256']})
        return result

    @mcp.tool()
    def edit_file(path:str,old_text:str,new_text:str,expected_replacements:int=1,expected_sha256:str|None=None)->dict[str,Any]:
        p=resolve_existing(path)
        if not p.is_file(): raise FileNotFoundError(str(p))
        text=p.read_text(encoding='utf-8',errors='strict'); count=text.count(old_text)
        if count!=int(expected_replacements): raise RuntimeError(f'REPLACEMENT_COUNT_MISMATCH: expected {expected_replacements}, found {count}')
        before=sha256_file(p); result=atomic_write(p,text.replace(old_text,new_text).encode('utf-8'),expected_sha256)
        audit('edit_file',str(p),details={'before_sha256':before,'after_sha256':result['sha256'],'replacements':count}); result['replacements']=count
        return result

    @mcp.tool()
    def move_file(source:str,destination:str)->dict[str,Any]:
        src=resolve_existing(source); dst=resolve_write(destination); dst.parent.mkdir(parents=True,exist_ok=True)
        os.replace(src,dst); audit('move_file',str(dst),details={'source':str(src)}); return {'source':str(src),'destination':str(dst)}

def _service_action(name:str,action:str)->dict[str,Any]:
    name=_service_name(name); init=_init_system()
    if init=='systemd': cmd=['systemctl',action,name]
    elif init=='openrc': cmd=['rc-service',name,action]
    else: raise RuntimeError('No supported service manager is available')
    p=subprocess.run(cmd,text=True,capture_output=True,check=False,timeout=60)
    out,tr=truncate((p.stdout or '')+(p.stderr or '')); audit(f'service_{action}',name,result='ok' if p.returncode==0 else 'error')
    return {'service':name,'action':action,'backend':init,'exit_code':p.returncode,'output':out,'truncated':tr}

@mcp.tool()
def service_status(name:str)->dict[str,Any]:
    name=_service_name(name); init=_init_system()
    if init=='systemd':
        props=subprocess.run(['systemctl','show',name,'--no-pager','--property=ActiveState,SubState,MainPID,MemoryCurrent,NRestarts,UnitFileState'],
          text=True,capture_output=True,check=False,timeout=20)
        data={}
        for line in props.stdout.splitlines():
            k,sep,v=line.partition('=')
            if sep:data[k]=v
        return {'service':name,'backend':'systemd','exit_code':props.returncode,'properties':data}
    if init=='openrc':
        p=subprocess.run(['rc-service',name,'status'],text=True,capture_output=True,check=False,timeout=20)
        out,tr=truncate((p.stdout or '')+(p.stderr or '')); return {'service':name,'backend':'openrc','exit_code':p.returncode,'status':out,'truncated':tr}
    raise RuntimeError('No supported service manager is available')

@mcp.tool()
def service_logs(name:str,lines:int=100)->dict[str,Any]:
    name=_service_name(name); lines=max(1,min(int(lines),2000))
    if _init_system()=='systemd' and shutil.which('journalctl'):
        p=subprocess.run(['journalctl','-u',name,'-n',str(lines),'--no-pager','--output=short-iso'],text=True,capture_output=True,check=False,timeout=60)
        out,tr=truncate((p.stdout or '')+(p.stderr or '')); return {'service':name,'backend':'journald','exit_code':p.returncode,'output':out,'truncated':tr}
    raise RuntimeError('No universal log backend is available')

if SERVICE_CONTROL_ENABLED:
    @mcp.tool()
    def service_start(name:str)->dict[str,Any]: return _service_action(name,'start')
    @mcp.tool()
    def service_stop(name:str)->dict[str,Any]: return _service_action(name,'stop')
    @mcp.tool()
    def service_restart(name:str)->dict[str,Any]: return _service_action(name,'restart')

def _read_process(pid:int)->dict[str,Any]|None:
    try:
        status={}
        for line in (Path('/proc')/str(pid)/'status').read_text(errors='replace').splitlines():
            k,sep,v=line.partition(':')
            if sep and k in {'Name','State','PPid','Uid','VmRSS','Threads'}:status[k]=v.strip()
        stat=(Path('/proc')/str(pid)/'stat').read_text().split()
        uid=int(status.get('Uid','-1').split()[0])
        try:user=pwd.getpwuid(uid).pw_name
        except Exception:user=str(uid)
        rss=status.get('VmRSS','0 kB').split()
        hz=os.sysconf(os.sysconf_names['SC_CLK_TCK']); boot=time.time()-float(Path('/proc/uptime').read_text().split()[0])
        start=boot+(int(stat[21])/hz)
        return {'pid':pid,'ppid':int(status.get('PPid','0')),'user':user,'state':status.get('State',''),'name':status.get('Name',''),
          'rss_kib':int(rss[0]) if rss and rss[0].isdigit() else 0,'threads':int(status.get('Threads','0')),'start_time':int(start),'elapsed_seconds':max(0,int(time.time()-start))}
    except (FileNotFoundError,ProcessLookupError,PermissionError,ValueError,IndexError): return None

@mcp.tool()
def process_list(limit:int=200)->dict[str,Any]:
    limit=max(1,min(int(limit),2000)); items=[]
    for e in Path('/proc').iterdir():
        if e.name.isdigit():
            x=_read_process(int(e.name))
            if x:items.append(x)
    items.sort(key=lambda x:(-x['rss_kib'],x['pid']))
    return {'processes':items[:limit],'count':len(items),'truncated':len(items)>limit}

if PROCESS_ENABLED:
    @mcp.tool()
    def start_process(argv:list[str],cwd:str='/',)->dict[str,Any]:
        command=_command_argv(argv); target=resolve_existing(cwd)
        if not target.is_dir(): raise NotADirectoryError(str(target))
        result=sessions.start(command,str(target),_exec_environment()); audit('start_process',str(result['pid']),details={'executable':command[0]}); return result
    @mcp.tool()
    def read_process_output(session_id:str,max_lines:int=200)->dict[str,Any]:
        result=sessions.read(session_id,max_lines)
        result['stdout']=redact(result.get('stdout','')); result['stderr']=redact(result.get('stderr',''))
        return result
    @mcp.tool()
    def send_process_input(session_id:str,data:str)->dict[str,Any]: return sessions.send(session_id,data)
    @mcp.tool()
    def kill_process(session_id:str,force:bool=False)->dict[str,Any]:
        result=sessions.terminate(session_id,force); audit('kill_process',session_id,details={'force':force}); return result
    @mcp.tool()
    def list_sessions()->dict[str,Any]: return {'sessions':sessions.list_all()}

@mcp.tool()
def listening_ports(limit:int=500)->dict[str,Any]:
    p=subprocess.run(['ss','-lntup'],text=True,capture_output=True,check=False,timeout=15) if shutil.which('ss') else None
    if p is None: raise RuntimeError('ss is not available')
    out,tr=truncate(p.stdout,max(4096,min(MAX_CAPTURE,int(limit)*300))); return {'output':out,'truncated':tr,'exit_code':p.returncode}

@mcp.tool()
def tcp_probe(host:str,port:int,timeout_seconds:float=5.0)->dict[str,Any]:
    started=time.monotonic()
    try:
        with socket.create_connection((host,int(port)),timeout=max(.1,min(float(timeout_seconds),30))):
            return {'host':host,'port':int(port),'ok':True,'latency_ms':round((time.monotonic()-started)*1000,2)}
    except OSError as exc:return {'host':host,'port':int(port),'ok':False,'latency_ms':round((time.monotonic()-started)*1000,2),'error':str(exc)}

@mcp.tool()
def http_probe(url:str,timeout_seconds:float=10.0)->dict[str,Any]:
    started=time.monotonic(); req=urllib.request.Request(url,method='GET',headers={'User-Agent':'ServerBridge/1'})
    try:
        with urllib.request.urlopen(req,timeout=max(.1,min(float(timeout_seconds),30))) as resp:
            return {'url':url,'ok':True,'status':resp.status,'latency_ms':round((time.monotonic()-started)*1000,2),'final_url':resp.geturl(),
              'content_type':resp.headers.get('Content-Type')}
    except Exception as exc:return {'url':url,'ok':False,'latency_ms':round((time.monotonic()-started)*1000,2),'error':str(exc)}

if EXEC_ENABLED:
    @mcp.tool()
    def run_command(argv:list[str],cwd:str='/',timeout_seconds:int=120)->dict[str,Any]:
        command=_command_argv(argv); target=resolve_existing(cwd)
        if not target.is_dir():raise NotADirectoryError(str(target))
        timeout=max(1,min(int(timeout_seconds),EXEC_MAX_TIMEOUT)); started=time.monotonic()
        with tempfile.TemporaryFile() as out_f,tempfile.TemporaryFile() as err_f:
            proc=subprocess.Popen(command,cwd=target,stdin=subprocess.DEVNULL,stdout=out_f,stderr=err_f,env=_exec_environment(),start_new_session=True,close_fds=True)
            timed_out=False
            try:proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True
                try:os.killpg(proc.pid,15)
                except ProcessLookupError:pass
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:os.killpg(proc.pid,9)
                    except ProcessLookupError:pass
                    proc.wait(timeout=5)
            out_f.seek(0);err_f.seek(0)
            stdout,st=truncate(out_f.read(MAX_CAPTURE+1).decode('utf-8',errors='replace')); stderr,et=truncate(err_f.read(MAX_CAPTURE+1).decode('utf-8',errors='replace'))
        audit('run_command',command[0],result='timeout' if timed_out else ('ok' if proc.returncode==0 else 'error'),details={'argument_count':len(command)})
        return {'executable':command[0],'argument_count':len(command),'cwd':str(target),'exit_code':None if timed_out else proc.returncode,
          'timed_out':timed_out,'timeout_seconds':timeout,'duration_seconds':round(time.monotonic()-started,3),'stdout':stdout,'stderr':stderr,
          'stdout_truncated':st,'stderr_truncated':et}

if __name__=='__main__':mcp.run()
