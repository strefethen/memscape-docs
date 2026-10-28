"""Dependency-free integrity checks for the standalone product page."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re
import struct
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "index.html"


class ProductDocument(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class ProductPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PAGE.read_text()
        cls.document = ProductDocument()
        cls.document.feed(cls.source)
        cls.elements = cls.document.elements

    def test_document_semantics(self):
        self.assertIn(("html", {"lang": "en"}), self.elements)
        self.assertEqual(sum(tag == "h1" for tag, _ in self.elements), 1)
        self.assertEqual(sum(tag == "main" for tag, _ in self.elements), 1)
        ids = [attrs["id"] for _, attrs in self.elements if "id" in attrs]
        self.assertEqual([key for key, count in Counter(ids).items() if count > 1], [])
        for tag, attrs in self.elements:
            if tag == "img":
                self.assertIn("alt", attrs)
                self.assertIn("width", attrs)
                self.assertIn("height", attrs)

    def test_local_links_assets_and_controls_resolve(self):
        ids = {attrs["id"] for _, attrs in self.elements if "id" in attrs}
        for tag, attrs in self.elements:
            for attribute in ("src", "srcset", "href"):
                if attribute not in attrs:
                    continue
                destination = urlsplit(attrs[attribute])
                if tag == "script" and attribute == "src" and attrs == {
                    "defer": None,
                    "data-domain": "mem.scapedeck.com",
                    "src": "https://analytics.ca-17.com/js/script.js",
                }:
                    continue
                self.assertFalse(destination.scheme or destination.netloc,
                                 "Only the approved Plausible script may be external")
                if destination.path:
                    self.assertTrue((PAGE.parent / destination.path).is_file(), attrs[attribute])
                if destination.fragment:
                    self.assertIn(destination.fragment, ids)
            if "aria-controls" in attrs:
                self.assertIn(attrs["aria-controls"], ids)
        # CSS assets must also resolve without relying on third-party hosts.
        css = (PAGE.parent / "assets/product.css").read_text()
        self.assertNotIn("@import", css)
        for destination in re.findall(r"url\(['\"]?([^)'\"]+)", css):
            self.assertTrue((PAGE.parent / "assets" / destination).is_file())

    def test_static_default_and_availability(self):
        elements = {attrs["id"]: attrs for _, attrs in self.elements if "id" in attrs}
        self.assertNotIn("hidden", elements["view-timeline"])
        self.assertIn("hidden", elements["view-calendar"])
        self.assertIn("hidden", elements["view-photos"])
        self.assertIn("In development", self.source)
        self.assertIn("Actual MemScape screenshots", self.source)
        self.assertNotIn("data/DayOne", self.source)
        self.assertNotIn("<form", self.source)

    def test_product_visuals_use_full_real_captures(self):
        manifest = json.loads((PAGE.parent / "assets/screenshots/capture.json").read_text())
        self.assertEqual(manifest["fixtureFlag"], "-memscape-showcase-journal")
        self.assertRegex(manifest["appCommit"], r"^[0-9a-f]{40}$")
        self.assertEqual(manifest["dimensions"], [1206, 2622])
        sources = {urlsplit(attrs["srcset"]).path for tag, attrs in self.elements if tag == "source"}
        self.assertEqual(sources, {
            f"assets/screenshots/{name}-dark.png" for name in ("home", "entry", "calendar", "photos", "tags", "colors")
        })
        for name in ("home", "entry", "calendar", "photos", "tags", "colors"):
            for appearance in ("light", "dark"):
                path = PAGE.parent / f"assets/screenshots/{name}-{appearance}.png"
                header = path.read_bytes()[:24]
                self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", header[16:24]), (1206, 2622))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 manifest["screenshots"][path.name]["sha256"])
        for invented in ("forest.svg", "memory-row", "calendar-days", "app-heading", "island"):
            self.assertNotIn(invented, self.source)

    def test_memory_copy_and_current_features(self):
        self.assertIn("<title>MemScape — A place for your memories.</title>", self.source)
        self.assertIn('property="og:title" content="MemScape — A place for your memories."', self.source)
        self.assertIn("A place for<br>your memories.</h1>", self.source)
        self.assertIn("<p>A place for your memories.</p>", self.source)
        self.assertNotIn("Shipped the build", self.source)
        self.assertNotIn("A place for your days", self.source)
        self.assertIn("visual map", self.source)
        self.assertIn("twelve tag colors", self.source)
        self.assertIn("photos are AI-generated", self.source)
        for name in ("tags", "colors"):
            self.assertIn(f'assets/screenshots/{name}-light.png', self.source)

    def test_supporting_pages_and_navigation(self):
        for name in ("privacy-policy.html", "support.html"):
            source = (PAGE.parent / name).read_text()
            document = ProductDocument()
            document.feed(source)
            self.assertEqual(sum(tag == "h1" for tag, _ in document.elements), 1)
            ids = {attrs["id"] for _, attrs in document.elements if "id" in attrs}
            for tag, attrs in document.elements:
                for attribute in ("src", "href"):
                    if attribute not in attrs:
                        continue
                    destination = urlsplit(attrs[attribute])
                    if destination.scheme:
                        if destination.scheme == "mailto":
                            self.assertEqual(attribute, "href")
                            self.assertEqual(destination.path, "support@commutedash.com")
                            continue
                        self.assertEqual(destination.scheme, "https")
                        self.assertEqual(attribute, "href")
                        continue
                    if destination.path:
                        self.assertTrue((PAGE.parent / destination.path).is_file())
                    elif destination.fragment:
                        self.assertIn(destination.fragment, ids)
            self.assertIn(f'href="{name}"', self.source)
            self.assertIn('href="mailto:support@commutedash.com"', source)
        policy = (PAGE.parent / "privacy-policy.html").read_text()
        self.assertIn("TestFlight Beta Testing", policy)
        self.assertIn('href="support.html"', policy)


if __name__ == "__main__":
    unittest.main()
