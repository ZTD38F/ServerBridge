from __future__ import annotations
import asyncio, os, tempfile
from pathlib import Path
os.environ['SERVERBRIDGE_ENABLE_EXEC']='1'
os.environ['SERVERBRIDGE_ENABLE_WRITE']='1'
os.environ['SERVERBRIDGE_ENABLE_PROCESS']='1'
os.environ['SERVERBRIDGE_ENABLE_SERVICE_CONTROL']='1'
from mcp import Client
from serverbridge.server import mcp

EXPECTED={'server_info','file_stat','list_files','read_file','read_text','search_files','search_text',
'write_file','edit_file','move_file','service_status','service_logs','service_start','service_stop','service_restart',
'process_list','start_process','read_process_output','send_process_input','kill_process','list_sessions',
'listening_ports','tcp_probe','http_probe','run_command'}

async def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['SERVERBRIDGE_ALLOWED_ROOTS']=tmp
        os.environ['SERVERBRIDGE_PROTECTED_PATHS']=''
        async with Client(mcp,raise_exceptions=True) as client:
            names={t.name for t in (await client.list_tools()).tools}
            missing=EXPECTED-names
            assert not missing,sorted(missing)
            p=Path(tmp)/'a.txt'; p.write_text('alpha\nbeta\n',encoding='utf-8')
            for name,args in [
              ('file_stat',{'path':str(p)}),
              ('read_file',{'path':str(p),'offset':0,'length':1}),
              ('search_files',{'root':tmp,'pattern':'*.txt'}),
              ('search_text',{'root':tmp,'query':'beta'}),
              ('write_file',{'path':str(Path(tmp)/'b.txt'),'content':'one\ntwo\n'}),
              ('edit_file',{'path':str(Path(tmp)/'b.txt'),'old_text':'two','new_text':'three'}),
              ('run_command',{'argv':['python3','-c','print(123)'],'cwd':tmp,'timeout_seconds':10}),
            ]:
                result=await client.call_tool(name,arguments=args); assert not result.is_error,(name,result)
            result=await client.call_tool('start_process',arguments={'argv':['python3','-u','-c','import sys; print(\"ready\",flush=True); print(sys.stdin.readline().strip(),flush=True)'],'cwd':tmp})
            assert not result.is_error
            payload=result.structured_content or {}
            sid=payload.get('session_id')
            assert sid,payload
            await asyncio.sleep(.1)
            assert not (await client.call_tool('send_process_input',arguments={'session_id':sid,'data':'hello\n'})).is_error
            await asyncio.sleep(.1)
            out=await client.call_tool('read_process_output',arguments={'session_id':sid,'max_lines':20})
            assert 'hello' in str(out),out
if __name__=='__main__': asyncio.run(main())
