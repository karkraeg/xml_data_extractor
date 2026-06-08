# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run extractor
uv run python xml_extractor.py config.yaml
uv run python xml_extractor.py config.yaml --input ./data --output results.csv --format csv
uv run python xml_extractor.py config.yaml --debug

# Installed as script after uv sync
uv run xml_extractor config.yaml
```

No test suite exists yet.

## Architecture

Single-file tool: `xml_extractor.py`. No modules, no packages.

**Data flow:**

1. `main()` (Click CLI) → loads YAML config via `load_config()` → creates `XMLExtractor`
2. `XMLExtractor.extract()` → globs `*.xml` from input dir → calls `_process_file()` per file
3. `_process_file()` → parses XML with lxml → auto-detects + merges namespaces → runs `root_xpath` to find record elements → filters records via `_check_record_filters()` → calls `_process_record()` per element
4. `_process_record()` → calls `_extract_field()` per configured field → returns dict
5. `_extract_field()` → runs XPath → optionally applies `_apply_filter()`, `_apply_transform()`, `url_prefix`
6. `extract()` → collects all dicts → `_write_output()` via pandas → prints stats table

**Config YAML keys:**

| Key | Purpose |
|-----|---------|
| `root_xpath` | XPath selecting one element per output row |
| `fields` | List of `{column, xpath, separator, filter, transform, url_prefix, as_list}` |
| `namespaces` | Override/supplement auto-detected XML namespaces |
| `record_filters` | Pre-extraction filters (AND logic); see `RECORD_FILTERS.md` |
| `input_directory` | Default input dir (overridden by `--input`) |
| `output_file` | Default output path (overridden by `--output`) |
| `logging.missing_xpath_verbosity` | `"none"` / `"summary"` / `"detailed"` |
| `logging.skip_invalid_xml` | Boolean; default `true` |

**Field-level pipeline order:** XPath → `filter` → `transform` → `url_prefix` → join with `separator` (or return list if `as_list: true`)

**Output formats:** CSV, Excel, Parquet (native list columns), JSON. Lists are pipe-joined (`" | "`) for CSV/Excel.

**Namespace handling:** Namespaces are auto-extracted per file and merged with config namespaces (config takes priority). Merged result is stored on `self.namespaces` and reused for all XPath calls within that file.

**OAI-PMH deleted records:** Files where `root_xpath` matches nothing are checked for `oai:header[@status='deleted']`; if found, silently skipped instead of warning.

**Logging:** Loguru writes a `.log` file next to the output file (always DEBUG level). Console output is WARNING+ unless `--debug`.
