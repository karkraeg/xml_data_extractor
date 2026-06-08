"""Tests for xml_config_builder helper functions."""

import pytest
from lxml import etree

from xml_config_builder import (
    collect_namespaces,
    display_tag,
    make_attr_xpath,
    make_element_xpath,
    make_root_xpath,
    suggested_column,
    tag_to_qualified,
)


SAMPLE_XML = b"""<?xml version="1.0"?>
<OAI-PMH xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <oai_dc:dc>
    <dc:title lang="en">Test</dc:title>
    <dc:creator>Author</dc:creator>
  </oai_dc:dc>
</OAI-PMH>
"""

NS = {
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def parse():
    return etree.parse(__import__("io").BytesIO(SAMPLE_XML))


def get_element(xpath):
    return parse().xpath(xpath, namespaces=NS)[0]


# ── collect_namespaces ────────────────────────────────────────────────────────

def test_collect_namespaces_finds_prefixes():
    root = parse().getroot()
    ns = collect_namespaces(root)
    assert "oai_dc" in ns
    assert "dc" in ns
    assert ns["dc"] == "http://purl.org/dc/elements/1.1/"


def test_collect_namespaces_no_duplicates():
    root = parse().getroot()
    ns = collect_namespaces(root)
    uris = list(ns.values())
    assert len(uris) == len(set(uris))


# ── tag_to_qualified ──────────────────────────────────────────────────────────

def test_tag_to_qualified_with_namespace():
    tag = "{http://purl.org/dc/elements/1.1/}title"
    result = tag_to_qualified(tag, NS)
    assert result == "dc:title"


def test_tag_to_qualified_no_namespace():
    result = tag_to_qualified("title", NS)
    assert result == "title"


def test_tag_to_qualified_unknown_uri():
    tag = "{http://unknown.example.org/}foo"
    result = tag_to_qualified(tag, NS)
    assert result == "foo"


# ── make_element_xpath ────────────────────────────────────────────────────────

def test_make_element_xpath():
    el = get_element(".//dc:title", )
    result = make_element_xpath(el, NS)
    assert result == ".//dc:title/text()"


def test_make_element_xpath_no_prefix():
    xml = b"<root><child>text</child></root>"
    el = etree.parse(__import__("io").BytesIO(xml)).xpath("//child")[0]
    result = make_element_xpath(el, {})
    assert result == ".//child/text()"


# ── make_attr_xpath ───────────────────────────────────────────────────────────

def test_make_attr_xpath():
    el = get_element(".//dc:title")
    result = make_attr_xpath(el, NS, "lang")
    assert result == ".//dc:title/@lang"


# ── make_root_xpath ───────────────────────────────────────────────────────────

def test_make_root_xpath():
    el = get_element(".//oai_dc:dc")
    result = make_root_xpath(el, NS)
    assert result == ".//oai_dc:dc"
    assert "/text()" not in result


# ── display_tag ───────────────────────────────────────────────────────────────

def test_display_tag():
    el = get_element(".//dc:creator")
    result = display_tag(el, NS)
    assert result == "dc:creator"


# ── suggested_column ─────────────────────────────────────────────────────────

def test_suggested_column_element():
    el = get_element(".//dc:title")
    result = suggested_column(el, NS)
    assert result == "Title"


def test_suggested_column_attr():
    el = get_element(".//dc:title")
    result = suggested_column(el, NS, attr="lang")
    assert result == "Lang"


def test_suggested_column_strips_prefix():
    el = get_element(".//oai_dc:dc")
    result = suggested_column(el, NS)
    assert result == "Dc"
