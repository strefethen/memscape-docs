"""Public story integrity: navigation, approved assets and private-source boundary."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs" if (ROOT / "docs/index.html").exists() else ROOT


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class JourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SITE / "journey.html").read_text()
        cls.elements = Document(cls.source).elements
        cls.manifest = json.loads((SITE / "assets/journey/images.json").read_text())

    def test_semantics_and_chapters(self):
        self.assertIn(("html", {"lang": "en"}), self.elements)
        for tag in ("h1", "main"):
            self.assertEqual(sum(t == tag for t, _ in self.elements), 1)
        self.assertEqual(sum(t == "article" for t, _ in self.elements), 18)
        ids = [a["id"] for _, a in self.elements if "id" in a]
        self.assertEqual(len(ids), len(set(ids)))
        for tag, attrs in self.elements:
            if "aria-labelledby" in attrs:
                self.assertIn(attrs["aria-labelledby"], ids)
        self.assertIn('href="journey.html"', (SITE / "index.html").read_text())

    def test_links_resolve_and_external_hosts_are_bounded(self):
        external = {
            "https://mem.scapedeck.com/journey",
            "https://analytics.ca-17.com/js/script.js",
        }
        for _, attrs in self.elements:
            for key in ("src", "href"):
                if key not in attrs:
                    continue
                value = attrs[key]
                target = urlsplit(value)
                if target.scheme or target.netloc:
                    self.assertIn(value, external)
                    continue
                path = SITE / (target.path or "journey.html")
                self.assertTrue(path.is_file(), value)
                self.assertTrue(path.resolve().is_relative_to(SITE.resolve()))
                if target.fragment:
                    ids = {a.get("id") for _, a in Document(path.read_text()).elements}
                    self.assertIn(target.fragment, ids)

    def test_only_manifest_images_are_used_and_bytes_match(self):
        images = [a for tag, a in self.elements if tag == "img"]
        used = {Path(a["src"]).name for a in images}
        self.assertEqual(used, set(self.manifest["assets"]))
        self.assertEqual({p.name for p in (SITE / "assets/journey").iterdir()},
                         used | {"images.json", "story.css"})
        for attrs in images:
            self.assertTrue(attrs["alt"])
            path = SITE / attrs["src"]
            raw = path.read_bytes()
            record = self.manifest["assets"][path.name]
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
            self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
            dimensions = struct.unpack(">II", raw[16:24])
            self.assertEqual(dimensions, (int(attrs["width"]), int(attrs["height"])))
            self.assertEqual(dimensions, (record["width"], record["height"]))
            # No embedded textual or EXIF payload can carry removed private details.
            offset = 8
            while offset < len(raw):
                size = struct.unpack(">I", raw[offset:offset + 4])[0]
                kind = raw[offset + 4:offset + 8]
                self.assertNotIn(kind, (b"tEXt", b"iTXt", b"zTXt", b"eXIf"))
                offset += size + 12

    def test_privacy_boundary_and_editorial_requirements(self):
        public_text = self.source + json.dumps(self.manifest)
        for private in ("/Users/", "/private/tmp", "t3-thread:", "data/DayOne",
                        "github.com/strefethen/daytwo", "tkt.stevetrefethen.com",
                        "sourcesResolved", "originalSource", "Source trail"):
            self.assertNotIn(private, public_text)
        for word in ("harness configuration", "Tier 2 tickets", "tkt CLI",
                     "Journaling Suggestions", "Live Activity", "redacted"):
            self.assertIn(word, self.source)
        self.assertNotIn("worth an Apple Design Award", self.source)
        for name in ("entry-before.png", "first-new-post.png"):
            if name in self.manifest["assets"]:
                record = self.manifest["assets"][name]
                self.assertTrue(record["redactions"], name)
                self.assertIn("redacted", record["caption"].lower())


if __name__ == "__main__":
    unittest.main()
