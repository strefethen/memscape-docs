"""Reject unsafe or incomplete deployment snapshots."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from demo_snapshot import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        for name in ('demo', 'fixtures'):
            shutil.copytree(ROOT / name, self.root / name)
        self.manifest = json.loads((ROOT / 'demo-manifest.json').read_text())
        self.tracked = set(self.manifest['files']) | {'demo-manifest.json'}
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        (self.root / 'demo-manifest.json').write_text(json.dumps(self.manifest))

    def test_valid_snapshot(self):
        self.assertEqual(validate_snapshot(self.root, self.tracked), set(self.manifest['files']))

    def test_tampered_file(self):
        (self.root / 'demo/index.html').write_text('altered')
        with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)

    def test_missing_module(self):
        (self.root / 'demo/pkg/memscape_web.js').unlink()
        with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)

    def test_untracked_file(self):
        self.tracked.remove('demo/bootstrap.js')
        with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)

    def test_unknown_file(self):
        (self.root / 'demo/private.json').write_text('{}')
        with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)

    def test_symlink(self):
        (self.root / 'demo/leak').symlink_to(self.root / 'demo/index.html')
        with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)

    def test_hostile_manifest_paths(self):
        for name in ('../private.txt', '/etc/passwd', 'demo/../../private.txt', 'demo/private.json'):
            with self.subTest(name=name):
                self.manifest['files'][name] = hashlib.sha256(b'').hexdigest()
                self.save()
                with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked | {name})
                del self.manifest['files'][name]


if __name__ == '__main__':
    unittest.main()
