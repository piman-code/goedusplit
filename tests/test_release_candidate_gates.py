"""Required outputs and preservation gates, with entirely synthetic candidates."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import json
from pathlib import Path
import plistlib
import subprocess
import os
import sys
import tempfile
import unittest
from build_scripts.release_manifest import digest, filenames, verify_pair, validate_platform
from build_scripts.repair_qtwebengine_macos import repair
from build_scripts.build_identity import record, verify
from unittest.mock import patch


class CandidateGates(unittest.TestCase):
    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root=Path(self.scratch.name)
        self.commit='a'*40
        for target, os_name, arch in [('macos','Darwin','arm64'),('windows','Windows','AMD64')]:
            hashes={}
            for name in filenames('1.0.6',target)+[f'USER_GUIDE-{target}.md']:
                p=self.root/name; p.write_bytes(b'synthetic candidate only')
                hashes[name]=digest(p)
            m={'source_commit':self.commit,'version':'1.0.6','source_clean':True,'target':target,
               'os_system':os_name,'architecture':arch,'files':hashes}
            m['build_identity']={k:m[k] for k in ('source_commit','version','source_clean','target')}
            m['build_identity']['executable_sha256']='c'*64
            (self.root/f'BUILD-{target}.json').write_text(json.dumps(m))

    def edit_manifest(self, target, **changes):
        p=self.root/f'BUILD-{target}.json'; m=json.loads(p.read_text()); m.update(changes);p.write_text(json.dumps(m))

    def test_same_source_pair_creates_checksums_and_preserves_existing_manifest(self):
        verify_pair(self.root,'1.0.6',self.commit)
        sums=(self.root/'SHA256SUMS').read_bytes()
        with self.assertRaises(ValueError): verify_pair(self.root,'1.0.6',self.commit)
        self.assertEqual((self.root/'SHA256SUMS').read_bytes(),sums)

    def test_wrong_commit_or_architecture_never_creates_success_manifest(self):
        for changes in [{'source_commit':'b'*40},{'architecture':'ARM64'},{'source_clean':False}]:
            with self.subTest(changes=changes):
                self.edit_manifest('windows',source_commit=self.commit,architecture='AMD64',source_clean=True)
                self.edit_manifest('windows',**changes)
                with self.assertRaises(ValueError): verify_pair(self.root,'1.0.6',self.commit)
                self.assertFalse((self.root/'SHA256SUMS').exists())

    def test_missing_setup_changed_bytes_or_extra_payload_blocks_pair(self):
        p=self.root/'Goedu-Split-1.0.6-windows-setup.exe';p.write_bytes(b'changed')
        with self.assertRaises(ValueError): verify_pair(self.root,'1.0.6',self.commit)
        p.unlink()
        with self.assertRaises(ValueError): verify_pair(self.root,'1.0.6',self.commit)
        self.assertFalse((self.root/'SHA256SUMS').exists())

    def test_unexpected_payload_is_rejected_without_reading_it(self):
        (self.root/'unapproved-folder').mkdir()
        with self.assertRaisesRegex(ValueError,'Unexpected files'): verify_pair(self.root,'1.0.6',self.commit)

    def test_platform_identity(self):
        with self.assertRaises(ValueError): validate_platform('macos','Darwin','x86_64')
        with self.assertRaises(ValueError): validate_platform('windows','Darwin','AMD64')

    def test_missing_qtwebengine_is_an_error(self):
        with self.assertRaises(RuntimeError): repair(self.root/'dist'/'Goedu-Split.app')

    def test_build_mac_preserves_existing_outputs(self):
        if not shutil_available_bash(): self.skipTest('bash is unavailable')
        project=Path(__file__).resolve().parents[1]
        scripts=self.root/'build_scripts'; scripts.mkdir()
        (self.root/'dist').mkdir()
        sentinel=self.root/'dist'/'keep'; sentinel.write_bytes(b'keep candidate')
        (scripts/'build_mac.sh').write_bytes((project/'build_scripts/build_mac.sh').read_bytes())
        result=subprocess.run(['bash',str(scripts/'build_mac.sh')],capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(sentinel.read_bytes(),b'keep candidate')

    def test_mac_pack_rejects_old_bundle_before_creating_dmg(self):
        if not shutil_available_bash(): self.skipTest('bash is unavailable')
        project=Path(__file__).resolve().parents[1]
        scripts=self.root/'build_scripts';scripts.mkdir()
        (scripts/'pack_mac.sh').write_bytes((project/'build_scripts/pack_mac.sh').read_bytes())
        (self.root/'app').mkdir()
        (self.root/'app/__init__.py').write_text('__version__="1.0.6"\n')
        contents=self.root/'dist/Goedu-Split.app/Contents';contents.mkdir(parents=True)
        with (contents/'Info.plist').open('wb') as out:
            plistlib.dump({'CFBundleVersion':'1.0.5','CFBundleShortVersionString':'1.0.5'},out)
        result=subprocess.run(['bash',str(scripts/'pack_mac.sh')],capture_output=True,
                              env={**os.environ,'GOEDUSPLIT_BUILD_PYTHON':sys.executable})
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'App bundle version differs',result.stderr)
        self.assertFalse((self.root/'dist/Goedu-Split-1.0.6-mac.dmg').exists())

    def test_build_identity_rejects_changed_executable_and_old_version(self):
        app=self.root/'dist/Goedu-Split';app.mkdir(parents=True)
        binary=app/'Goedu-Split.exe';binary.write_bytes(b'synthetic executable')
        identity={'source_commit':self.commit,'source_clean':True}
        with patch('build_scripts.build_identity.source_identity',return_value=identity):
            record(self.root,app,'windows')
            verify(self.root,app,'windows','1.0.6')
            with self.assertRaises(ValueError): verify(self.root,app,'windows','1.0.7')
            binary.write_bytes(b'replaced executable')
            with self.assertRaises(ValueError): verify(self.root,app,'windows','1.0.6')


def shutil_available_bash():
    import shutil
    return shutil.which('bash')
