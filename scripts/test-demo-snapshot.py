"""Reject unsafe or incomplete deployment snapshots."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from demo_snapshot import validate_snapshot, APP_MANIFEST, ICON

ROOT = Path(__file__).resolve().parents[1]


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        for name in ('demo', 'fixtures'):
            shutil.copytree(ROOT / name, self.root / name)
        (self.root / 'assets').mkdir()
        shutil.copyfile(ROOT / ICON, self.root / ICON)
        self.manifest = json.loads((ROOT / 'demo-manifest.json').read_text())
        self.tracked = set(self.manifest['files']) | {'demo-manifest.json', ICON}
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

    def replace_runtime(self, name, data):
        (self.root / name).write_bytes(data)
        self.manifest['files'][name] = hashlib.sha256(data).hexdigest()
        self.save()

    def test_mandatory_card_and_manifest_boundaries(self):
        for name in ('demo/assets/demo-social-v1.png', 'demo/manifest.webmanifest'):
            original = (self.root / name).read_bytes()
            with self.subTest(name=name):
                self.tracked.remove(name)
                with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
                self.tracked.add(name)
                (self.root / name).write_bytes(b'tampered')
                with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
                self.replace_runtime(name, b'{}')
                with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
                (self.root / name).unlink()
                with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
                (self.root / name).symlink_to(self.root / 'demo/index.html')
                with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
                (self.root / name).unlink()
                self.replace_runtime(name, original)
                expected = self.manifest['files'].pop(name)
                self.save()
                with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
                self.manifest['files'][name] = expected
                self.save()

    def test_exact_manifest_contract(self):
        name = 'demo/manifest.webmanifest'
        original = (self.root / name).read_bytes()
        cases = [b'{', b'null', original.replace(b'"name":', b'"name":"other","name":', 1)]
        for key in APP_MANIFEST:
            changed = dict(APP_MANIFEST); changed.pop(key)
            cases.append(json.dumps(changed).encode())
            cases.append(json.dumps(dict(APP_MANIFEST, **{key:'wrong'})).encode())
        for key, value in [('scope','/'),('id','/demo/#new'),('start_url','/demo/?build=1'),('serviceworker',{})]:
            cases.append(json.dumps(dict(APP_MANIFEST, **{key:value})).encode())
        for key, value in [('sizes','192x192'),('purpose','maskable'),('type','image/jpeg'),('src','/wrong.png')]:
            changed = dict(APP_MANIFEST, icons=[dict(APP_MANIFEST['icons'][0], **{key:value})])
            cases.append(json.dumps(changed).encode())
        for data in cases:
            with self.subTest(data=data):
                self.replace_runtime(name, data)
                with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)

    def test_icon_boundary(self):
        original = (self.root / ICON).read_bytes()
        self.tracked.remove(ICON)
        with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
        self.tracked.add(ICON)
        for data in (b'bad', original[:16]+b'\x00'*8+original[24:], original[:-1]+bytes([original[-1]^1])):
            (self.root / ICON).write_bytes(data)
            with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
        (self.root / ICON).unlink()
        with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
        (self.root / ICON).symlink_to(self.root / 'demo/assets/demo-social-v1.png')
        with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)

    def test_raw_head_contract(self):
        name = 'demo/index.html'
        original = (self.root / name).read_text()
        anchors = ['<link rel="manifest" href="/demo/manifest.webmanifest">',
                   '<meta name="apple-mobile-web-app-title" content="MemScape Demo">',
                   '<meta name="apple-mobile-web-app-capable" content="yes">',
                   '<meta name="mobile-web-app-capable" content="yes">',
                   '<meta name="apple-mobile-web-app-status-bar-style" content="default">']
        for anchor in anchors:
            for replacement in ('',anchor+anchor):
                self.replace_runtime(name,original.replace(anchor,replacement).encode())
                with self.assertRaises(ValueError): validate_snapshot(self.root, self.tracked)
        for before, after in [('https://mem.scapedeck.com/demo/', 'http://localhost/demo/'),
                              ('MemScape Demo — Explore the Journal App','wrong'),
                              ('https://mem.scapedeck.com/assets/app-icon.png','/assets/wrong.png'),
                              ('content="1200"','content="512"')]:
            self.replace_runtime(name,original.replace(before,after).encode())
            with self.assertRaises(ValueError): validate_snapshot(self.root,self.tracked)

    def test_precise_header_changes(self):
        headers = (ROOT / '_headers').read_text()
        expected = "https://mem.scapedeck.com/*\n  Cache-Control: public, max-age=0, must-revalidate, no-transform\n\n/demo/*\n  Content-Security-Policy: default-src 'none'; script-src 'self' 'wasm-unsafe-eval' https://analytics.ca-17.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://analytics.ca-17.com; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; manifest-src 'self'\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n\n/demo/manifest.webmanifest\n  Content-Type: application/manifest+json\n"
        self.assertEqual(headers, expected)


if __name__ == '__main__':
    unittest.main()
