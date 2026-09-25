from __future__ import annotations
import hashlib, json, os, re, tempfile, time
from pathlib import Path
from typing import Any

SECRET_PATTERNS = [
    re.compile(r'(?i)(authorization:\s*bearer\s+)[^\s]+'),
    re.compile(r'(?i)((?:password|token|api[_-]?key|secret)\s*[=:]\s*)[^\s]+'),
    re.compile(r'\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b'),
]

def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1','true','yes','on'}

EXEC_ENABLED = env_bool('SERVERBRIDGE_ENABLE_EXEC')
WRITE_ENABLED = env_bool('SERVERBRIDGE_ENABLE_WRITE', EXEC_ENABLED)
PROCESS_ENABLED = env_bool('SERVERBRIDGE_ENABLE_PROCESS', EXEC_ENABLED)
SERVICE_CONTROL_ENABLED = env_bool('SERVERBRIDGE_ENABLE_SERVICE_CONTROL', EXEC_ENABLED)
MAX_CAPTURE = int(os.getenv('SERVERBRIDGE_MAX_CAPTURE_BYTES', '65536'))
MAX_HASH_BYTES = int(os.getenv('SERVERBRIDGE_MAX_HASH_BYTES', str(64*1024*1024)))

def allowed_roots() -> list[Path]:
    raw = os.getenv('SERVERBRIDGE_ALLOWED_ROOTS','/')
    roots=[Path(x.strip()).expanduser().resolve(strict=False) for x in raw.split(':') if x.strip()]
    return roots or [Path('/')]

def protected_paths() -> list[Path]:
    raw=os.getenv('SERVERBRIDGE_PROTECTED_PATHS',
        '/etc/serverbridge/runtime.env:/etc/serverbridge/network.env:/etc/serverbridge/network.sh:/etc/serverbridge/tunnel-client')
    return [Path(x.strip()).expanduser().resolve(strict=False) for x in raw.split(':') if x.strip()]

def _inside(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            pass
    return False

def resolve_existing(path: str) -> Path:
    resolved=Path(path).expanduser().resolve(strict=True)
    if _inside(resolved, protected_paths()):
        raise PermissionError(f'Path is protected from MCP file tools: {resolved}')
    if not _inside(resolved, allowed_roots()):
        raise PermissionError(f'Path is outside SERVERBRIDGE_ALLOWED_ROOTS: {resolved}')
    return resolved

def resolve_write(path: str) -> Path:
    raw=Path(path).expanduser()
    parent=raw.parent.resolve(strict=True)
    candidate=(parent/raw.name).resolve(strict=False)
    if _inside(candidate, protected_paths()):
        raise PermissionError(f'Path is protected from MCP file tools: {candidate}')
    if not _inside(candidate, allowed_roots()):
        raise PermissionError(f'Path is outside SERVERBRIDGE_ALLOWED_ROOTS: {candidate}')
    return candidate

def sha256_file(path: Path) -> str | None:
    size=path.stat().st_size
    if size > MAX_HASH_BYTES:
        return None
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def redact(value: str) -> str:
    out=value
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            out=pattern.sub(lambda m:(m.group(1) if m.lastindex else '')+'[REDACTED]', out)
        else:
            out=pattern.sub('[REDACTED]', out)
    return out

def truncate(value: str, limit: int = MAX_CAPTURE) -> tuple[str,bool]:
    raw=value.encode('utf-8',errors='replace')
    if len(raw)<=limit:
        return redact(value),False
    return redact(raw[:limit].decode('utf-8',errors='replace')+'\n…[truncated]'),True

def atomic_write(path: Path, data: bytes, expected_sha256: str|None=None) -> dict[str,Any]:
    if path.exists() and expected_sha256 is not None:
        current=sha256_file(path)
        if current != expected_sha256:
            raise RuntimeError(f'CONFLICT: expected sha256 {expected_sha256}, current {current}')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=f'.{path.name}.',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.chmod(tmp, path.stat().st_mode & 0o7777 if path.exists() else 0o640)
        os.replace(tmp,path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
    return {'path':str(path),'size':len(data),'sha256':sha256_file(path)}

def _redact_obj(value: Any) -> Any:
    if isinstance(value,str): return redact(value)
    if isinstance(value,dict): return {str(k):_redact_obj(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_redact_obj(v) for v in value]
    return value

def audit(tool: str, target: str, result: str='ok', details: dict[str,Any]|None=None) -> None:
    record=_redact_obj({'ts':int(time.time()),'tool':tool,'target':target,'result':result,'details':details or {}})
    path=Path(os.getenv('SERVERBRIDGE_AUDIT_LOG','/var/lib/serverbridge/audit.jsonl'))
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf-8') as f:
            f.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n')
    except OSError:
        pass
