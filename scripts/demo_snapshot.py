"""Validate the consumed, versioned simulation snapshot before staging."""
import hashlib
import json
from pathlib import Path
import re

STATIC = {'demo/index.html', 'demo/bootstrap.js', 'demo/memscape.css',
          'demo/pkg/memscape_web.js', 'demo/pkg/memscape_web_bg.wasm',
          'demo/third-party-notices.txt', 'demo/rust-library-notices.html'} | {
    f'demo/styles/{name}.css' for name in ('shell', 'entry', 'editor', 'browse', 'photos', 'calendar', 'settings')}
SNIPPET = re.compile(r'demo/pkg/snippets/(?:memscape-web-[a-f0-9]+/inline[0-9]+\.js|pdl-render-[a-f0-9]+/src/mapkit_adapter\.js)')
PHOTO = re.compile(r'fixtures/showcase/journal/photos/[A-F0-9-]{36}\.jpg')


def regular(path):
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f'Snapshot path must be a regular file: {path}')
    return path.read_bytes()


def validate_snapshot(root, tracked):
    manifest_name = 'demo-manifest.json'
    if manifest_name not in tracked:
        raise ValueError('Track the demo manifest before staging')
    manifest = json.loads(regular(root / manifest_name))
    if manifest['format'] != 1 or not re.fullmatch(r'[a-f0-9]{40}', manifest['source_commit']):
        raise ValueError('Invalid demo provenance')
    files = manifest['files']
    if not isinstance(files, dict) or not STATIC <= files.keys():
        raise ValueError('Missing mandatory demo assets')
    if sum(bool(PHOTO.fullmatch(n)) for n in files) != 8:
        raise ValueError('Expected eight synthetic photos')
    for name, expected in files.items():
        if name not in STATIC and not SNIPPET.fullmatch(name) and not PHOTO.fullmatch(name):
            raise ValueError(f'Unapproved public snapshot path: {name}')
        if name not in tracked:
            raise ValueError(f'Untracked snapshot file: {name}')
        if hashlib.sha256(regular(root / name)).hexdigest() != expected:
            raise ValueError(f'Snapshot hash mismatch: {name}')
    actual = set()
    for directory in ('demo', 'fixtures'):
        for path in (root / directory).rglob('*'):
            if path.is_symlink():
                raise ValueError(f'Snapshot symlink: {path}')
            if path.is_file():
                actual.add(path.relative_to(root).as_posix())
    if actual != set(files):
        raise ValueError(f'Unexpected or missing snapshot files: {actual ^ set(files)}')
    return set(files)
