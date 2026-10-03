"""Authenticated Streamable HTTP runtime for a ServerBridge generation."""
from __future__ import annotations
import argparse,hmac,json,os
from pathlib import Path
import uvicorn
from . import __version__, sessions
from .server import mcp

TOKEN_FILE=Path(os.environ.get("SERVERBRIDGE_BACKEND_TOKEN_FILE","/etc/serverbridge/backend_token"))

def token()->str:
    v=TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(v)<32: raise RuntimeError("invalid backend secret")
    return v

def hdrs(scope):
    return {k.decode("latin1").lower():v.decode("latin1") for k,v in scope.get("headers",[])}

async def out(send,status,obj):
    b=json.dumps(obj,separators=(",",":")).encode()
    await send({"type":"http.response.start","status":status,"headers":[(b"content-type",b"application/json"),(b"content-length",str(len(b)).encode()),(b"cache-control",b"no-store")]})
    await send({"type":"http.response.body","body":b})

base=mcp.streamable_http_app(streamable_http_path="/mcp",json_response=True,stateless_http=True,host="127.0.0.1")

class App:
    async def __call__(self,scope,receive,send):
        if scope["type"]=="lifespan": return await base(scope,receive,send)
        if scope["type"]!="http": return await base(scope,receive,send)
        try: ok=hmac.compare_digest(token(),hdrs(scope).get("x-bridge-backend-token",""))
        except Exception: ok=False
        if not ok: return await out(send,403,{"ok":False,"error":"forbidden"})
        p=scope.get("path","")
        if p=="/healthz": return await out(send,200,{"ok":True,"pid":os.getpid(),"version":__version__})
        if p=="/__bridge/runtime-status":
            live=sum(1 for s in sessions.list_all() if s.get("running"))
            return await out(send,200,{"ok":True,"pid":os.getpid(),"live_process_sessions":live,"version":__version__})
        return await base(scope,receive,send)

def main():
    a=argparse.ArgumentParser();a.add_argument("--port",type=int,required=True);ns=a.parse_args()
    token();uvicorn.run(App(),host="127.0.0.1",port=ns.port,log_level="warning",access_log=False)

if __name__=="__main__": main()
