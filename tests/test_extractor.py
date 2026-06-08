"""Tests for XMLExtractor core logic."""

import textwrap
from io import BytesIO
from pathlib import Path

import pytest
from lxml import etree

from xml_extractor import XMLExtractor, load_config


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <OAI-PMH xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
             xmlns:dc="http://purl.org/dc/elements/1.1/">
      <GetRecord>
        <record>
          <metadata>
            <oai_dc:dc>
              <dc:title>Test Title</dc:title>
              <dc:creator>Author One</dc:creator>
              <dc:creator>Author Two</dc:creator>
              <dc:identifier>urn:nbn:de:test-123</dc:identifier>
              <dc:identifier>https://example.com/test</dc:identifier>
              <dc:date>2024-01-15</dc:date>
              <dc:type>doc-type:article</dc:type>
            </oai_dc:dc>
          </metadata>
        </record>
      </GetRecord>
    </OAI-PMH>
""").encode()


NS = {
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

BASE_CONFIG = {
    "root_xpath": ".//oai_dc:dc",
    "namespaces": NS,
    "fields": [],
}


def make_extractor(extra_config: dict = None) -> XMLExtractor:
    cfg = {**BASE_CONFIG, **(extra_config or {})}
    return XMLExtractor(cfg)


def get_dc_element() -> etree._Element:
    tree = etree.parse(BytesIO(SAMPLE_XML))
    return tree.xpath(".//oai_dc:dc", namespaces=NS)[0]


# ── _apply_filter ─────────────────────────────────────────────────────────────

class TestApplyFilter:
    def setup_method(self):
        self.ext = make_extractor()
        self.values = ["urn:nbn:de:test-123", "https://example.com/test", "10.1234/abc"]

    def test_startswith(self):
        result = self.ext._apply_filter(self.values, {"type": "startswith", "pattern": "urn:nbn"})
        assert result == ["urn:nbn:de:test-123"]

    def test_contains(self):
        result = self.ext._apply_filter(self.values, {"type": "contains", "pattern": "example.com"})
        assert result == ["https://example.com/test"]

    def test_regex(self):
        result = self.ext._apply_filter(self.values, {"type": "regex", "pattern": r"^10\."})
        assert result == ["10.1234/abc"]

    def test_regex_no_match_returns_empty(self):
        result = self.ext._apply_filter(self.values, {"type": "regex", "pattern": "nomatch"})
        assert result == []

    def test_unknown_type_returns_original(self):
        result = self.ext._apply_filter(self.values, {"type": "unknown", "pattern": "x"})
        assert result == self.values

    def test_no_filter_returns_original(self):
        assert self.ext._apply_filter(self.values, None) == self.values

    def test_empty_values(self):
        assert self.ext._apply_filter([], {"type": "startswith", "pattern": "x"}) == []

    def test_missing_pattern_returns_original(self):
        result = self.ext._apply_filter(self.values, {"type": "startswith"})
        assert result == self.values


# ── _apply_transform ──────────────────────────────────────────────────────────

class TestApplyTransform:
    def setup_method(self):
        self.ext = make_extractor()

    def test_full_match(self):
        result = self.ext._apply_transform(["hello world"], {"regex": r"\w+"})
        assert result == ["hello"]

    def test_capture_group(self):
        result = self.ext._apply_transform(
            ["180830e20180830abc"],
            {"regex": r"e(\d{4})(\d{2})(\d{2})", "group": 1},
        )
        assert result == ["2018"]

    def test_format_string(self):
        result = self.ext._apply_transform(
            ["180830e20180830abc"],
            {"regex": r"e(\d{4})(\d{2})(\d{2})", "format": "{0}-{1}-{2}"},
        )
        assert result == ["2018-08-30"]

    def test_no_match_excluded(self):
        result = self.ext._apply_transform(["no-date-here"], {"regex": r"e(\d{8})"})
        assert result == []

    def test_invalid_regex_returns_original(self):
        result = self.ext._apply_transform(["abc"], {"regex": r"[invalid"})
        assert result == ["abc"]

    def test_empty_transform_returns_original(self):
        assert self.ext._apply_transform(["abc"], {}) == ["abc"]


# ── _extract_field ────────────────────────────────────────────────────────────

class TestExtractField:
    def setup_method(self):
        self.ext = make_extractor()
        self.ext.namespaces = NS
        self.el = get_dc_element()

    def test_single_value(self):
        result = self.ext._extract_field(
            self.el, {"column": "Title", "xpath": ".//dc:title/text()"}, "test.xml"
        )
        assert result == "Test Title"

    def test_multiple_values_joined(self):
        result = self.ext._extract_field(
            self.el, {"column": "Creators", "xpath": ".//dc:creator/text()"}, "test.xml"
        )
        assert result == "Author One | Author Two"

    def test_custom_separator(self):
        result = self.ext._extract_field(
            self.el,
            {"column": "Creators", "xpath": ".//dc:creator/text()", "separator": "; "},
            "test.xml",
        )
        assert result == "Author One; Author Two"

    def test_as_list(self):
        result = self.ext._extract_field(
            self.el,
            {"column": "Creators", "xpath": ".//dc:creator/text()", "as_list": True},
            "test.xml",
        )
        assert result == ["Author One", "Author Two"]

    def test_filter_applied(self):
        result = self.ext._extract_field(
            self.el,
            {
                "column": "URN",
                "xpath": ".//dc:identifier/text()",
                "filter": {"type": "startswith", "pattern": "urn:"},
            },
            "test.xml",
        )
        assert result == "urn:nbn:de:test-123"

    def test_url_prefix(self):
        result = self.ext._extract_field(
            self.el,
            {
                "column": "URL",
                "xpath": ".//dc:identifier/text()",
                "filter": {"type": "startswith", "pattern": "urn:"},
                "url_prefix": "https://resolver.de/",
            },
            "test.xml",
        )
        assert result == "https://resolver.de/urn:nbn:de:test-123"

    def test_missing_xpath_returns_empty(self):
        result = self.ext._extract_field(
            self.el, {"column": "Missing", "xpath": ".//dc:missing/text()"}, "test.xml"
        )
        assert result == ""

    def test_no_xpath_returns_empty(self):
        result = self.ext._extract_field(self.el, {"column": "Bad"}, "test.xml")
        assert result == ""

    def test_transform_applied(self):
        result = self.ext._extract_field(
            self.el,
            {
                "column": "Type",
                "xpath": ".//dc:type/text()",
                "transform": {"regex": r"doc-type:(\w+)", "group": 1},
            },
            "test.xml",
        )
        assert result == "article"


# ── _check_record_filters ─────────────────────────────────────────────────────

class TestCheckRecordFilters:
    def setup_method(self):
        self.ext = make_extractor()
        self.ext.namespaces = NS
        self.el = get_dc_element()

    def _check(self, filters):
        self.ext.config["record_filters"] = filters
        return self.ext._check_record_filters(self.el, "test.xml")

    def test_no_filters_passes(self):
        assert self.ext._check_record_filters(self.el, "test.xml") is True

    def test_exists_pass(self):
        assert self._check([{"xpath": ".//dc:title/text()", "condition": "exists"}]) is True

    def test_exists_fail(self):
        assert self._check([{"xpath": ".//dc:missing/text()", "condition": "exists"}]) is False

    def test_not_exists_pass(self):
        assert self._check([{"xpath": ".//dc:missing/text()", "condition": "not_exists"}]) is True

    def test_not_exists_fail(self):
        assert self._check([{"xpath": ".//dc:title/text()", "condition": "not_exists"}]) is False

    def test_equals_pass(self):
        assert self._check([{"xpath": ".//dc:title/text()", "condition": "equals", "value": "Test Title"}]) is True

    def test_equals_fail(self):
        assert self._check([{"xpath": ".//dc:title/text()", "condition": "equals", "value": "Other"}]) is False

    def test_not_equals_pass(self):
        assert self._check([{"xpath": ".//dc:title/text()", "condition": "not_equals", "value": "Other"}]) is True

    def test_contains_pass(self):
        assert self._check([{"xpath": ".//dc:identifier/text()", "condition": "contains", "value": "urn:nbn"}]) is True

    def test_contains_fail(self):
        assert self._check([{"xpath": ".//dc:identifier/text()", "condition": "contains", "value": "nomatch"}]) is False

    def test_not_contains_pass(self):
        assert self._check([{"xpath": ".//dc:identifier/text()", "condition": "not_contains", "value": "nomatch"}]) is True

    def test_matches_pass(self):
        assert self._check([{"xpath": ".//dc:date/text()", "condition": "matches", "value": r"^\d{4}-\d{2}-\d{2}$"}]) is True

    def test_matches_fail(self):
        assert self._check([{"xpath": ".//dc:date/text()", "condition": "matches", "value": r"^\d{8}$"}]) is False

    def test_not_matches_pass(self):
        assert self._check([{"xpath": ".//dc:date/text()", "condition": "not_matches", "value": r"^\d{8}$"}]) is True

    def test_date_after_pass(self):
        assert self._check([{"xpath": ".//dc:date/text()", "condition": "date_after", "value": "2020-01-01"}]) is True

    def test_date_after_fail(self):
        assert self._check([{"xpath": ".//dc:date/text()", "condition": "date_after", "value": "2025-01-01"}]) is False

    def test_date_before_pass(self):
        assert self._check([{"xpath": ".//dc:date/text()", "condition": "date_before", "value": "2025-01-01"}]) is True

    def test_in_pass(self):
        assert self._check([{"xpath": ".//dc:title/text()", "condition": "in", "value": ["Test Title", "Other"]}]) is True

    def test_in_fail(self):
        assert self._check([{"xpath": ".//dc:title/text()", "condition": "in", "value": ["Other"]}]) is False

    def test_not_in_pass(self):
        assert self._check([{"xpath": ".//dc:title/text()", "condition": "not_in", "value": ["Other"]}]) is True

    def test_multiple_filters_all_must_pass(self):
        filters = [
            {"xpath": ".//dc:title/text()", "condition": "exists"},
            {"xpath": ".//dc:date/text()", "condition": "date_after", "value": "2020"},
            {"xpath": ".//dc:missing/text()", "condition": "exists"},  # this fails
        ]
        assert self._check(filters) is False


# ── load_config ───────────────────────────────────────────────────────────────

class TestLoadConfig:
    def test_valid_config(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "root_xpath: .//dc:dc\nfields:\n  - column: Title\n    xpath: .//dc:title/text()\n"
        )
        cfg = load_config(cfg_file)
        assert cfg["root_xpath"] == ".//dc:dc"
        assert len(cfg["fields"]) == 1

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_missing_root_xpath(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("fields:\n  - column: Title\n    xpath: .//title\n")
        with pytest.raises(ValueError, match="root_xpath"):
            load_config(cfg_file)

    def test_missing_fields(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("root_xpath: .//dc:dc\n")
        with pytest.raises(ValueError, match="fields"):
            load_config(cfg_file)

    def test_empty_fields(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("root_xpath: .//dc:dc\nfields: []\n")
        with pytest.raises(ValueError):
            load_config(cfg_file)


# ── Integration ───────────────────────────────────────────────────────────────

class TestIntegration:
    def test_full_extraction(self, tmp_path):
        xml_file = tmp_path / "sample.xml"
        xml_file.write_bytes(SAMPLE_XML)

        cfg = {
            "root_xpath": ".//oai_dc:dc",
            "namespaces": NS,
            "fields": [
                {"column": "Title", "xpath": ".//dc:title/text()"},
                {"column": "Creators", "xpath": ".//dc:creator/text()"},
                {"column": "URN", "xpath": ".//dc:identifier/text()",
                 "filter": {"type": "startswith", "pattern": "urn:"}},
            ],
        }

        ext = XMLExtractor(cfg)
        records = ext._process_file(xml_file)

        assert len(records) == 1
        assert records[0]["Title"] == "Test Title"
        assert records[0]["Creators"] == "Author One | Author Two"
        assert records[0]["URN"] == "urn:nbn:de:test-123"

    def test_record_filter_excludes(self, tmp_path):
        xml_file = tmp_path / "sample.xml"
        xml_file.write_bytes(SAMPLE_XML)

        cfg = {
            "root_xpath": ".//oai_dc:dc",
            "namespaces": NS,
            "fields": [{"column": "Title", "xpath": ".//dc:title/text()"}],
            "record_filters": [
                {"xpath": ".//dc:date/text()", "condition": "date_after", "value": "2025-01-01"}
            ],
        }

        ext = XMLExtractor(cfg)
        records = ext._process_file(xml_file)

        assert records == []
        assert ext.stats["records_filtered"] == 1

    def test_output_csv(self, tmp_path):
        xml_file = tmp_path / "sample.xml"
        xml_file.write_bytes(SAMPLE_XML)
        out = tmp_path / "out.csv"

        cfg = {
            "root_xpath": ".//oai_dc:dc",
            "namespaces": NS,
            "fields": [{"column": "Title", "xpath": ".//dc:title/text()"}],
            "input_directory": str(tmp_path),
            "output_file": str(out),
        }

        ext = XMLExtractor(cfg)
        ext.extract(tmp_path, out, "csv")

        assert out.exists()
        content = out.read_text()
        assert "Test Title" in content
