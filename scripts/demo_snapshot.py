"""Validate the consumed, versioned simulation snapshot before staging."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct

STATIC = {'demo/index.html', 'demo/bootstrap.js', 'demo/memscape.css',
          'demo/pkg/memscape_web.js', 'demo/pkg/memscape_web_bg.wasm',
          'demo/third-party-notices.txt', 'demo/rust-library-notices.html',
          'demo/assets/demo-social-v1.png', 'demo/manifest.webmanifest'} | {
    f'demo/styles/{name}.css' for name in ('shell', 'entry', 'editor', 'browse', 'photos', 'calendar', 'settings')}
SNIPPET = re.compile(r'demo/pkg/snippets/(?:memscape-web-[a-f0-9]+/inline[0-9]+\.js|pdl-render-[a-f0-9]+/src/mapkit_adapter\.js)')
STORY_IMAGE = re.compile(r'fixtures/journey/images/[a-z0-9-]+\.png')
PHOTO = re.compile(r'fixtures/showcase/journal/photos/[A-F0-9-]{36}\.jpg')
ICON = 'assets/app-icon.png'
CARD_SHA256 = '9b0c530ca8c8a9530cbb45a81756682af7b71d13d8eca8471ec4be9fbf368d76'
ICON_SHA256 = '150a30dbf67d1b0700cd2c0649c4dd149d0de1da04f09111ea18a420806e219e'
APP_MANIFEST = {'name': 'MemScape Demo', 'short_name': 'MemScape Demo',
                'id': '/demo/', 'start_url': '/demo/', 'scope': '/demo/',
                'display': 'standalone', 'lang': 'en', 'theme_color': '#ffffff',
                'background_color': '#ffffff',
                'icons': [{'src': '/assets/app-icon.png', 'sizes': '1024x1024',
                           'type': 'image/png', 'purpose': 'any'}]}


class Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_head = False
        self.tags = []
        self.title = ''
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == 'head': self.in_head = True
        if self.in_head: self.tags.append((tag, dict(attrs)))
        if tag == 'title': self.in_title = True

    def handle_endtag(self, tag):
        if tag == 'head': self.in_head = False
        if tag == 'title': self.in_title = False

    def handle_data(self, data):
        if self.in_title: self.title += data


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON member: {key}')
        result[key] = value
    return result


def validate_public_metadata(root, tracked):
    app_manifest = json.loads(regular(root / 'demo/manifest.webmanifest'), object_pairs_hook=unique_object)
    if app_manifest != APP_MANIFEST:
        raise ValueError('Invalid Home Screen manifest contract')
    if ICON not in tracked:
        raise ValueError('Untracked app icon')
    for name, expected, width, height, size in [
        (ICON, ICON_SHA256, 1024, 1024, 53201),
        ('demo/assets/demo-social-v1.png', CARD_SHA256, 1200, 630, 347175)]:
        data = regular(root / name)
        if (hashlib.sha256(data).hexdigest() != expected or len(data) != size or
            data[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' or
            struct.unpack('>II', data[16:24]) != (width, height)):
            raise ValueError(f'Invalid approved PNG bytes/dimensions: {name}')
    html = regular(root / 'demo/index.html').decode()
    head = Head(); head.feed(html)
    canonical = 'https://mem.scapedeck.com/demo/'
    title = 'MemScape Demo — Explore the Journal App'
    description = ("Explore how MemScape was built through its development journal, historical screenshots, and visual calendar. "
                   'Changes last only for this session and reset on reload.')
    image = canonical + 'assets/demo-social-v1.png'
    alt = 'MemScape demo showing fictional journal entries, colored tags, and a beach memory.'
    expected_meta = {
        'description': description, 'robots': 'index,follow,max-image-preview:large',
        'apple-mobile-web-app-title': 'MemScape Demo', 'apple-mobile-web-app-capable': 'yes',
        'mobile-web-app-capable': 'yes', 'apple-mobile-web-app-status-bar-style': 'default',
        'og:title': title, 'og:description': description, 'og:url': canonical, 'og:type': 'website',
        'og:site_name': 'MemScape', 'og:image': image, 'og:image:width': '1200', 'og:image:height': '630',
        'og:image:type': 'image/png', 'og:image:alt': alt, 'twitter:card': 'summary_large_image',
        'twitter:title': title, 'twitter:description': description, 'twitter:image': image, 'twitter:image:alt': alt}
    if head.title != title or sum(t == 'title' for t, _ in head.tags) != 1 or 'localhost' in html:
        raise ValueError('Invalid published title/origin')
    for name, value in expected_meta.items():
        matches = [a for t, a in head.tags if t == 'meta' and name in (a.get('name'), a.get('property'))]
        if len(matches) != 1 or matches[0].get('content') != value:
            raise ValueError(f'Invalid publication metadata: {name}')
    for rel, href in [('canonical', canonical), ('manifest', '/demo/manifest.webmanifest'),
                      ('icon', 'https://mem.scapedeck.com/assets/app-icon.png'),
                      ('apple-touch-icon', 'https://mem.scapedeck.com/assets/app-icon.png')]:
        matches = [a for t, a in head.tags if t == 'link' and rel in a.get('rel', '').lower().split()]
        if len(matches) != 1 or matches[0].get('href') != href:
            raise ValueError(f'Invalid publication link: {rel}')
    themes = [a for t, a in head.tags if t == 'meta' and a.get('name') == 'theme-color']
    if themes != [{'name': 'theme-color', 'content': '#ffffff', 'media': '(prefers-color-scheme: light)'},
                  {'name': 'theme-color', 'content': '#000000', 'media': '(prefers-color-scheme: dark)'}]:
        raise ValueError('Invalid publication theme colors')
    scripts = [a for t, a in head.tags if t == 'script']
    if sum(a.get('src') == 'https://analytics.ca-17.com/js/script.js' and
           a.get('data-domain') == 'mem.scapedeck.com' for a in scripts) != 1:
        raise ValueError('Invalid demo analytics')


def regular(path):
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f'Snapshot path must be a regular file: {path}')
    return path.read_bytes()


def validate_snapshot(root, tracked):
    manifest_name = 'demo-manifest.json'
    if manifest_name not in tracked:
        raise ValueError('Track the demo manifest before staging')
    manifest = json.loads(regular(root / manifest_name), object_pairs_hook=unique_object)
    if manifest['format'] != 1 or not re.fullmatch(r'[a-f0-9]{40}', manifest['source_commit']):
        raise ValueError('Invalid demo provenance')
    files = manifest['files']
    if not isinstance(files, dict) or not STATIC <= files.keys():
        raise ValueError('Missing mandatory demo assets')
    if sum(bool(PHOTO.fullmatch(n)) for n in files) != 8:
        raise ValueError('Expected eight synthetic photos')
    if sum(bool(STORY_IMAGE.fullmatch(n)) for n in files) != 16:
        raise ValueError('Expected sixteen approved story images')
    for name, expected in files.items():
        if name not in STATIC and not SNIPPET.fullmatch(name) and not PHOTO.fullmatch(name) and not STORY_IMAGE.fullmatch(name):
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
    validate_public_metadata(root, tracked)
    return set(files)
