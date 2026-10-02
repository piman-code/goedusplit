"""Bind a freshly built executable to source identity before packaging it."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import __version__


def executable(app, target):
    return app/'Contents/MacOS/Goedu-Split' if target=='macos' else app/'Goedu-Split.exe'


def hash_file(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def source_identity(root):
    if (root/'.git').exists():
        sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True).strip()
        return {'source_commit':sha,'source_clean':not bool(dirty)}
    identity = json.loads((root/'WINDOWS_SOURCE_IDENTITY.json').read_text(encoding='utf-8'))
    if identity.get('version') != __version__ or not re.fullmatch(r'[0-9a-f]{40}',identity.get('source_commit','')):
        raise ValueError('Invalid development kit source identity')
    files=identity.get('file_sha256')
    if not isinstance(files,dict) or not files:
        raise ValueError('Missing development kit file identities')
    allowed_roots={'app','assets','build_scripts','distribution','docs','tests'}
    allowed_files={'run.py','run_tests.py','requirements.txt','requirements-build-lock.txt','goedusplit.spec',
                   'README.md','SECURITY.md','.gitignore','.gitattributes','WINDOWS_DEV_KIT_MANIFEST.txt'}
    for name,expected in files.items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or (path.parts[0] not in allowed_roots and name not in allowed_files):
            raise ValueError('Invalid development kit source path')
        candidate=root/path
        if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in [candidate,*candidate.parents]) or not candidate.is_file():
            raise ValueError('Missing or linked development kit source')
        if hash_file(candidate)!=expected:
            raise ValueError('Development kit source changed after snapshot')
    return {'source_commit':identity['source_commit'],'source_clean':True}


def marker_path(app,target):
    return app.parent/'BUILD_SOURCE-macos.json' if target=='macos' else app/'BUILD_SOURCE.json'


def record(root,app,target):
    binary=executable(app,target)
    if binary.is_symlink() or getattr(binary,'is_junction',lambda:False)() or not binary.is_file() or not binary.stat().st_size:
        raise ValueError('Required executable is missing or is a symlink')
    value={**source_identity(root),'version':__version__,'target':target,'executable_sha256':hash_file(binary)}
    with marker_path(app,target).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')
    return value


def verify(root,app,target,version=__version__):
    value=json.loads(marker_path(app,target).read_text(encoding='utf-8'))
    current=source_identity(root)
    if not current['source_clean'] or any(value.get(k)!=v for k,v in current.items()):
        raise ValueError('Source is dirty or differs from executable build source')
    if value.get('version')!=version or value.get('target')!=target:
        raise ValueError('Executable build version/target differs from source')
    if value.get('executable_sha256')!=hash_file(executable(app,target)):
        raise ValueError('Executable changed after build identity was recorded')
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',choices=['macos','windows'],required=True)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    if args.write: record(ROOT,args.app,args.target)
    else: verify(ROOT,args.app,args.target)
    print('Executable and source identity recorded.' if args.write else 'Executable and source identity verified.')
