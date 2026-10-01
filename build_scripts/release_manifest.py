"""Fail closed on incomplete candidates; record provenance and verify both platforms."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_scripts.build_identity import verify as verify_build

def validate_identity(version, commit):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected semantic version and full source SHA')

def validate_platform(target, os_name, architecture):
    allowed = {'macos': ('Darwin', {'arm64', 'aarch64'}), 'windows': ('Windows', {'amd64', 'x86_64'})}
    expected_os, expected_arch = allowed[target]
    if os_name != expected_os or architecture.lower() not in expected_arch:
        raise ValueError('Unsupported target OS/architecture')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def filenames(version, target):
    prefix = f'Goedu-Split-{version}'
    if target == 'macos':
        return [prefix + '-mac.dmg']
    if target == 'windows':
        return [prefix + '-windows.zip', prefix + '-windows-setup.exe']
    raise ValueError('Unknown target')


def collect(root, version, target, expected_commit, output):
    validate_identity(version, expected_commit)
    validate_platform(target, platform.system(), platform.machine())
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if commit != expected_commit:
        raise ValueError('Checkout commit does not match requested source')
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root, text=True)
    if dirty.strip():
        raise ValueError('Candidate requires a clean source checkout')
    actual = subprocess.check_output([sys.executable, '-B', '-c', 'from app import __version__; print(__version__)'], cwd=root, text=True).strip()
    if actual != version:
        raise ValueError('Requested candidate version differs from app version')
    app = root / 'dist' / ('Goedu-Split.app' if target == 'macos' else 'Goedu-Split')
    identity = verify_build(root, app, target, version)
    sources = [root / 'dist' / name for name in filenames(version, target)]
    sources += [root / 'distribution' / 'USER_GUIDE.md']
    for path in sources:
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f'Missing/empty/symlink required output: {path.name}')
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for source in sources:
        name = f'USER_GUIDE-{target}.md' if source.name == 'USER_GUIDE.md' else source.name
        shutil.copyfile(source, output / name)
        hashes[name] = digest(output / name)
    metadata = {'version':version, 'source_commit':commit, 'source_clean':True, 'target':target,
                'python':platform.python_version(), 'os':platform.platform(), 'os_system':platform.system(), 'architecture':platform.machine(),
                'node':subprocess.check_output(['node','--version'], text=True).strip(),
                'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
                'build_identity':identity, 'files':hashes, 'status':'build-candidate; real-PC and teacher validation pending'}
    (output / f'BUILD-{target}.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    return metadata


def verify_pair(folder, version, commit):
    validate_identity(version, commit)
    hashes = {}
    for target in ('macos', 'windows'):
        manifest = json.loads((folder / f'BUILD-{target}.json').read_text(encoding='utf-8'))
        validate_platform(target, manifest['os_system'], manifest['architecture'])
        if (manifest['version'], manifest['source_commit'], manifest['source_clean'], manifest['target']) != (version, commit, True, target):
            raise ValueError('Platform provenance mismatch')
        identity = manifest['build_identity']
        if any(identity.get(k) != manifest[k] for k in ('version','source_commit','source_clean','target')):
            raise ValueError('Executable source identity differs from platform provenance')
        if not re.fullmatch(r'[0-9a-f]{64}', identity.get('executable_sha256','')):
            raise ValueError('Missing executable checksum')
        expected = set(filenames(version, target)) | {f'USER_GUIDE-{target}.md'}
        if set(manifest['files']) != expected:
            raise ValueError('Required platform output set differs')
        for name, expected_hash in manifest['files'].items():
            path = folder / name
            if path.is_symlink() or not path.is_file() or not path.stat().st_size or digest(path) != expected_hash:
                raise ValueError(f'Candidate checksum mismatch: {name}')
            hashes[name] = expected_hash
        hashes[f'BUILD-{target}.json'] = digest(folder / f'BUILD-{target}.json')
    if set(p.name for p in folder.iterdir()) != set(hashes):
        raise ValueError('Unexpected files in combined candidate payload')
    if hashes['USER_GUIDE-macos.md'] != hashes['USER_GUIDE-windows.md']:
        raise ValueError('The two candidates contain different user guides')
    checksum = folder / 'SHA256SUMS'
    with checksum.open('x', encoding='utf-8') as stream:
        stream.write(''.join(f'{h}  {name}\n' for name,h in sorted(hashes.items())))
    return hashes


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--target', choices=['macos','windows'])
    parser.add_argument('--output', type=Path, default=Path('artifacts'))
    parser.add_argument('--verify-pair', type=Path)
    args=parser.parse_args()
    if args.verify_pair:
        verify_pair(args.verify_pair, args.version, args.commit)
    elif args.target:
        collect(ROOT,args.version,args.target,args.commit,args.output)
    else:
        parser.error('--target or --verify-pair is required')
    print('Candidate provenance and required files verified; real-PC acceptance remains separate.')
