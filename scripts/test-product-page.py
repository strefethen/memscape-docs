"""Dependency-free integrity checks for the standalone product page."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
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
                self.assertFalse(destination.scheme or destination.netloc,
                                 "The product page should be self-contained")
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
        sources = {attrs["srcset"] for tag, attrs in self.elements if tag == "source"}
        self.assertEqual(sources, {
            f"assets/screenshots/{name}-dark.png" for name in ("home", "entry", "calendar", "photos")
        })
        for name in ("home", "entry", "calendar", "photos"):
            for appearance in ("light", "dark"):
                path = PAGE.parent / f"assets/screenshots/{name}-{appearance}.png"
                header = path.read_bytes()[:24]
                self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", header[16:24]), (1206, 2622))
        for invented in ("forest.svg", "memory-row", "calendar-days", "app-heading", "island"):
            self.assertNotIn(invented, self.source)

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
                        self.assertEqual(destination.scheme, "https")
                        self.assertEqual(attribute, "href")
                        continue
                    if destination.path:
                        self.assertTrue((PAGE.parent / destination.path).is_file())
                    elif destination.fragment:
                        self.assertIn(destination.fragment, ids)
            self.assertIn(f'href="{name}"', self.source)
        policy = (PAGE.parent / "privacy-policy.html").read_text()
        self.assertIn("TestFlight Beta Testing", policy)
        self.assertIn('href="support.html"', policy)


if __name__ == "__main__":
    unittest.main()
