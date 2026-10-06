"""Transactional A/B updater for ServerBridge."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,tarfile,tempfile,time,urllib.request,uuid
from pathlib import Path

REPO="ZTD38F/ServerBridge"
ROOT=Path("/opt/serverbridge"); CONFIG=Path("/etc/serverbridge"); STATE=Path("/var/lib/serverbridge"); BIN=Path("/usr/local/lib/serverbridge")
ROUTE=STATE/"route.json"; JOURNAL=STATE/"update.json"; BACKEND_PID=STATE/"backend.pid"; SUPERVISOR_GENERATION=STATE/"supervisor-generation"
ROUTER_TOKEN=CONFIG/"router_token"; BACKEND_TOKEN=CONFIG/"backend_token"
LOCK=Path("/run/lock/serverbridge-seamless-update.lock"); LOG=Path("/var/log/serverbridge-update.log")
ROUTER="http://127.0.0.1:18766"

def log(msg):
    LOG.parent.mkdir(parents=True,exist_ok=True)
    with LOG.open("a") as f:f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())+" "+msg+"\n")

def api(path):
    req=urllib.request.Request("https://api.github.com"+path,headers={"User-Agent":"ServerBridge-Updater"})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)

def download(url,path):
    req=urllib.request.Request(url,headers={"User-Agent":"ServerBridge-Updater"})
    with urllib.request.urlopen(req,timeout=180) as r,open(path,"wb") as f:shutil.copyfileobj(r,f)

def secret(path):
    v=Path(path).read_text().strip()
    if len(v)<32:raise RuntimeError("invalid local secret")
    return v

def auth_json(url,header,token_file,method="GET",body=None):
    data=None if body is None else json.dumps(body,separators=(",",":")).encode()
    headers={header:secret(token_file)}
    if data is not None:
        headers["Content-Type"]="application/json";headers["Accept"]="application/json, text/event-stream"
    req=urllib.request.Request(url,data=data,method=method,headers=headers)
    with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)

def tools(base,header,token_file):
    auth_json(base+"/mcp",header,token_file,"POST",{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ServerBridgeUpdater","version":"1"}}})
    d=auth_json(base+"/mcp",header,token_file,"POST",{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
    return d["result"]["tools"]

def assert_compatible(old,new):
    n={t["name"]:t.get("inputSchema") for t in new}
    missing=[t["name"] for t in old if t["name"] not in n]
    changed=[t["name"] for t in old if t["name"] in n and t.get("inputSchema")!=n[t["name"]]]
    if missing or changed:raise RuntimeError(f"breaking tool contract missing={missing} changed={changed}")

def route():
    d=json.loads(ROUTE.read_text());return str(d["generation"]),int(d["port"])

def set_route(g,p):
    tmp=ROUTE.with_suffix(".tmp");tmp.write_text(json.dumps({"generation":g,"port":p},separators=(",",":"))+"\n");os.replace(tmp,ROUTE);ROUTE.chmod(0o600)

def alive(pid):
    try:os.kill(int(pid),0);return True
    except Exception:return False

def stop(pid):
    if not pid:return
    try:os.kill(int(pid),15)
    except Exception:return

def is_ancestor(pid):
    """True when pid is an ancestor of this updater process."""
    try:target=int(pid)
    except Exception:return False
    cur=os.getppid();seen=set()
    while cur>1 and cur not in seen:
        if cur==target:return True
        seen.add(cur)
        try:
            cur=int(Path(f"/proc/{cur}/stat").read_text().split()[3])
        except Exception:
            break
    return False

def defer_stop_after_drain(pid,generation):
    """Retire a self-hosting previous backend after its MCP response returns."""
    if not pid:return
    code=r"""
import json,os,pathlib,signal,sys,time,urllib.request
generation,pid_s,token_path,log_path=sys.argv[1:]
pid=int(pid_s);token=pathlib.Path(token_path).read_text().strip()
for _ in range(120):
    try:
        req=urllib.request.Request("http://127.0.0.1:18766/__bridge/status",headers={"X-Bridge-Token":token})
        with urllib.request.urlopen(req,timeout=3) as r:
            inflight=int(json.load(r).get("inflight",{}).get(generation,0))
        if inflight==0:
            try:os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:pass
            with open(log_path,"a",encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())+f" deferred old backend retired pid={pid}\\n")
            raise SystemExit(0)
    except Exception:
        pass
    time.sleep(.5)
with open(log_path,"a",encoding="utf-8") as f:
    f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())+f" WARNING deferred old backend retirement timed out pid={pid}\\n")
"""
    subprocess.Popen([sys.executable,"-c",code,str(generation),str(pid),str(ROUTER_TOKEN),str(LOG)],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        start_new_session=True,close_fds=True)
    log(f"deferred old backend retirement scheduled pid={pid}")

def write_state(phase,current,candidate,pg,pp,ppid,cp,cpid,failure="",rollback=""):
    tx=uuid.uuid4().hex
    if JOURNAL.exists():
        try:tx=json.loads(JOURNAL.read_text()).get("transaction_id") or tx
        except Exception:pass
    d={"transaction_id":tx,"update_kind":"RUNTIME_UPDATE","phase":phase,"current_generation":current,"candidate_generation":candidate,
       "previous_generation":pg,"previous_port":pp,"previous_pid":ppid,"candidate_port":cp,"candidate_pid":cpid,
       "failure_reason":failure,"rollback_reason":rollback,"updated_at":int(time.time())}
    tmp=JOURNAL.with_suffix(".tmp");tmp.write_text(json.dumps(d,separators=(",",":"))+"\n");os.replace(tmp,JOURNAL);JOURNAL.chmod(0o600)

def recover():
    if not JOURNAL.exists():return
    try:d=json.loads(JOURNAL.read_text())
    except Exception:return
    if d.get("phase") in ("","COMMITTED","FAILED_ROLLED_BACK","DEFERRED_STATEFUL_HANDLES"):return
    log("recover interrupted phase="+str(d.get("phase")))
    if d.get("previous_generation") and d.get("previous_port"):set_route(d["previous_generation"],int(d["previous_port"]))
    stop(d.get("candidate_pid",0))
    if alive(d.get("previous_pid",0)):BACKEND_PID.write_text(str(d["previous_pid"])+"\n")
    d["phase"]="FAILED_ROLLED_BACK";d["rollback_reason"]="interrupted update recovered";d["updated_at"]=int(time.time());JOURNAL.write_text(json.dumps(d,separators=(",",":"))+"\n")

def parse_env(path):
    out={}
    if not path.exists():return out
    for raw in path.read_text().splitlines():
        line=raw.strip()
        if not line or line.startswith("#") or "=" not in line:continue
        k,v=line.split("=",1);v=v.strip().strip('"').strip("'");out[k]=v
    return out

def stage_latest():
    rel=api(f"/repos/{REPO}/releases/latest")
    if rel.get("draft") or rel.get("prerelease"):raise RuntimeError("latest release not stable")
    tag=rel["tag_name"];commit=api(f"/repos/{REPO}/commits/{tag}")["sha"]
    if not isinstance(commit,str) or len(commit)!=40:raise RuntimeError("bad release commit")
    dest=ROOT/"releases"/commit
    if (dest/"serverbridge"/"http_runtime.py").exists():return commit,dest,tag
    assets={a["name"]:a for a in rel.get("assets",[])}
    tar_name=f"ServerBridge-{tag}.tar.gz"
    if tar_name not in assets or "SHA256SUMS.txt" not in assets:raise RuntimeError("release artifacts incomplete")
    with tempfile.TemporaryDirectory(prefix="serverbridge-update.") as td:
        td=Path(td);tar_path=td/tar_name;sums=td/"SHA256SUMS.txt"
        download(assets[tar_name]["browser_download_url"],tar_path);download(assets["SHA256SUMS.txt"]["browser_download_url"],sums)
        expected=None
        for line in sums.read_text().splitlines():
            parts=line.split()
            if len(parts)>=2 and parts[-1].lstrip("*")==tar_name:expected=parts[0].lower();break
        if not expected:raise RuntimeError("release checksum missing")
        actual=hashlib.sha256(tar_path.read_bytes()).hexdigest()
        if actual!=expected:raise RuntimeError("release checksum mismatch")
        extract=td/"src";extract.mkdir()
        with tarfile.open(tar_path,"r:gz") as tf:
            tf.extractall(extract, filter="data")
        children=[p for p in extract.iterdir() if p.is_dir()]
        src=children[0] if len(children)==1 else extract
        tmp=Path(str(dest)+".tmp");shutil.rmtree(tmp,ignore_errors=True);shutil.copytree(src,tmp)
        py=sys.executable
        subprocess.run([py,"-m","venv",str(tmp/".venv")],check=True)
        p=tmp/".venv"/"bin"/"python"
        subprocess.run([str(p),"-m","pip","install","--disable-pip-version-check","--no-input","--require-hashes","-r",str(tmp/"requirements.lock")],check=True,stdout=subprocess.DEVNULL)
        subprocess.run([str(p),"-m","pip","install","--disable-pip-version-check","--no-input","--no-deps",str(tmp)],check=True,stdout=subprocess.DEVNULL)
        subprocess.run([str(p),"-m","compileall","-q",str(tmp/"serverbridge")],check=True)
        os.replace(tmp,dest)
    return commit,dest,tag

def start_backend(release,port):
    env=os.environ.copy();env.update(parse_env(CONFIG/"serverbridge.env"));env.update(parse_env(CONFIG/"network.env"));env["SERVERBRIDGE_BACKEND_TOKEN_FILE"]=str(BACKEND_TOKEN)
    logf=open(f"/var/log/serverbridge-backend-{release.name[:12]}.log","ab",buffering=0)
    p=subprocess.Popen([str(release/".venv"/"bin"/"python"),"-m","serverbridge.http_runtime","--port",str(port)],cwd=str(release),env=env,stdin=subprocess.DEVNULL,stdout=logf,stderr=subprocess.STDOUT,start_new_session=True)
    return p

def backend_health(port):
    try:return auth_json(f"http://127.0.0.1:{port}/healthz","X-Bridge-Backend-Token",BACKEND_TOKEN).get("ok") is True
    except Exception:return False

def update_supervisor(candidate):
    generation=candidate.name
    try:
        if SUPERVISOR_GENERATION.read_text().strip()==generation:return True
    except Exception:pass
    s=auth_json(ROUTER+"/__bridge/status","X-Bridge-Token",ROUTER_TOKEN)
    if sum(int(v) for v in s.get("inflight",{}).values()):
        log("supervisor update deferred: inflight")
        return False
    subprocess.run(["systemctl","restart","serverbridge-supervisor.service"],check=True)
    for _ in range(30):
        try:
            if auth_json(ROUTER+"/__bridge/healthz","X-Bridge-Token",ROUTER_TOKEN).get("ok"):
                SUPERVISOR_GENERATION.write_text(generation+"\n");SUPERVISOR_GENERATION.chmod(0o600)
                return True
        except Exception:pass
        time.sleep(.2)
    raise RuntimeError("supervisor restart failed")

def normalize_transport_version(raw):
    token=(raw or "").strip().split()[0] if (raw or "").strip() else ""
    token=token.split("+",1)[0]
    if not token:return ""
    return token if token.startswith("v") else "v"+token

def update_transport(candidate):
    pin=(candidate/"TUNNEL_CLIENT_VERSION").read_text().strip()
    link=BIN/"tunnel-client"
    try:current=normalize_transport_version(subprocess.check_output([str(link),"--version"],text=True))
    except Exception:current=""
    if pin==current:return
    log(f"TRANSPORT_UPDATE {current}->{pin}")
    arch=os.uname().machine
    arch="arm64" if arch in ("aarch64","arm64") else "amd64"
    asset=f"tunnel-client-{pin}-linux-{arch}.zip";base=f"https://github.com/openai/tunnel-client/releases/download/{pin}"
    with tempfile.TemporaryDirectory(prefix="serverbridge-transport.") as td:
        td=Path(td);z=td/asset;s=td/"SHA256SUMS.txt";download(base+"/"+asset,z);download(base+"/SHA256SUMS.txt",s)
        expected=None
        for line in s.read_text().splitlines():
            if line.split()[-1].lstrip("*")==asset:expected=line.split()[0];break
        if not expected or hashlib.sha256(z.read_bytes()).hexdigest()!=expected:raise RuntimeError("transport checksum mismatch")
        import zipfile
        with zipfile.ZipFile(z) as q:q.extractall(td/"x")
        binary=next((td/"x").rglob("tunnel-client"))
        versioned=BIN/f"tunnel-client-{pin}";staged=BIN/f".tunnel-client-{pin}.new"
        shutil.copy2(binary,staged);staged.chmod(0o755);os.replace(staged,versioned)
    previous=Path(os.path.realpath(link))
    subprocess.run(["systemctl","stop","serverbridge.service"],check=True)
    tmp=BIN/".tunnel-client.new"
    try:
        if tmp.exists() or tmp.is_symlink():tmp.unlink()
        tmp.symlink_to(versioned.name);os.replace(tmp,link)
        subprocess.run(["systemctl","start","serverbridge.service"],check=True)
        for _ in range(30):
            if subprocess.run(["systemctl","is-active","--quiet","serverbridge.service"]).returncode==0:return
            time.sleep(1)
        raise RuntimeError("transport service failed")
    except Exception:
        subprocess.run(["systemctl","stop","serverbridge.service"],check=False)
        if tmp.exists() or tmp.is_symlink():tmp.unlink()
        tmp.symlink_to(previous.name);os.replace(tmp,link)
        subprocess.run(["systemctl","start","serverbridge.service"],check=False)
        raise

def main():
    import fcntl
    LOCK.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(LOCK,os.O_CREAT|os.O_RDWR,0o600)
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    STATE.mkdir(parents=True,exist_ok=True);recover()
    current=os.path.basename(os.path.realpath(ROOT/"current"))
    target,candidate,tag=stage_latest()
    if current==target:
        update_supervisor(candidate);update_transport(candidate)
        log("ok already current "+target);return
    pg,pp=route();ppid=int(BACKEND_PID.read_text().strip()) if BACKEND_PID.exists() else 0;cp=18772 if pp==18771 else 18771
    self_hosted=is_ancestor(ppid)
    drain_floor=1 if self_hosted else 0
    if self_hosted:log("self-hosted MCP update detected; allowing own in-flight request during drain")
    write_state("STAGED",current,target,pg,pp,ppid,cp,0)
    status=auth_json(f"http://127.0.0.1:{pp}/__bridge/runtime-status","X-Bridge-Backend-Token",BACKEND_TOKEN)
    if int(status.get("live_process_sessions",0))>0:
        write_state("DEFERRED_STATEFUL_HANDLES",current,target,pg,pp,ppid,cp,0);log("deferred stateful handles");return
    oldtools=tools(ROUTER,"X-Bridge-Token",ROUTER_TOKEN)
    p=start_backend(candidate,cp);write_state("CANDIDATE_STARTING",current,target,pg,pp,ppid,cp,p.pid)
    for _ in range(40):
        if p.poll() is None and backend_health(cp):break
        time.sleep(.25)
    if p.poll() is not None or not backend_health(cp):stop(p.pid);write_state("FAILED_PRE_SWITCH",current,target,pg,pp,ppid,cp,p.pid,"candidate health failed");raise RuntimeError("candidate unhealthy")
    newtools=tools(f"http://127.0.0.1:{cp}","X-Bridge-Backend-Token",BACKEND_TOKEN);assert_compatible(oldtools,newtools);write_state("CANDIDATE_HEALTHY",current,target,pg,pp,ppid,cp,p.pid)
    set_route(target,cp);write_state("SWITCHED",current,target,pg,pp,ppid,cp,p.pid)
    try:
        assert_compatible(oldtools,tools(ROUTER,"X-Bridge-Token",ROUTER_TOKEN));write_state("DRAINING_OLD",current,target,pg,pp,ppid,cp,p.pid)
        for _ in range(120):
            s=auth_json(ROUTER+"/__bridge/status","X-Bridge-Token",ROUTER_TOKEN)
            if int(s.get("inflight",{}).get(pg,0))<=drain_floor:break
            time.sleep(.5)
        else:raise RuntimeError("drain timeout")
        write_state("OBSERVING",current,target,pg,pp,ppid,cp,p.pid);time.sleep(3)
        if not backend_health(cp):raise RuntimeError("candidate failed observation")
        tools(ROUTER,"X-Bridge-Token",ROUTER_TOKEN)
    except Exception as e:
        set_route(pg,pp);stop(p.pid)
        if alive(ppid):
            BACKEND_PID.write_text(str(ppid)+"\n");BACKEND_PID.chmod(0o600)
        write_state("FAILED_ROLLED_BACK",current,target,pg,pp,ppid,cp,p.pid,str(e),"route and previous backend pointer restored");raise
    prev=ROOT/".previous.new"
    if prev.exists() or prev.is_symlink():prev.unlink()
    prev.symlink_to(Path(os.path.realpath(ROOT/"current")));os.replace(prev,ROOT/"previous")
    cur=ROOT/".current.new"
    if cur.exists() or cur.is_symlink():cur.unlink()
    cur.symlink_to(candidate);os.replace(cur,ROOT/"current")
    BACKEND_PID.write_text(str(p.pid)+"\n");BACKEND_PID.chmod(0o600)
    write_state("COMMITTED",current,target,pg,pp,ppid,cp,p.pid)
    if self_hosted:defer_stop_after_drain(ppid,pg)
    else:stop(ppid)
    update_supervisor(candidate);update_transport(candidate)
    log("ok seamless runtime activation "+target)

if __name__=="__main__":main()
