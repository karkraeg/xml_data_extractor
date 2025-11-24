#!/usr/bin/env python3
"""
XML Field Extractor - Flexible XML to CSV/Parquet converter
Supports complex XML formats like Dublin Core, METS, LIDO, PREMIS, etc.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import click
import pandas as pd
import yaml
from loguru import logger
from lxml import etree
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)
from rich.table import Table

console = Console()


class XMLExtractor:
    """Main extractor class for XML to CSV conversion."""

    def __init__(self, config: Dict[str, Any], debug: bool = False):
        self.config = config
        self.debug = debug
        # Initialize with config namespaces so they're always available
        self.namespaces: Dict[str, str] = config.get("namespaces", {}).copy()
        self.stats = {
            "files_processed": 0,
            "files_skipped": 0,
            "records_extracted": 0,
            "records_filtered": 0,
            "fields_missing": 0,
            "missing_fields_by_name": {},
            "errors": [],
        }

    def _extract_namespaces(self, tree: etree._ElementTree) -> Dict[str, str]:
        """Extract all namespaces from XML document."""
        nsmap = {}
        for ns_prefix, ns_uri in tree.getroot().nsmap.items():
            if ns_prefix is not None:
                nsmap[ns_prefix] = ns_uri
            else:
                # Handle default namespace
                nsmap["default"] = ns_uri
        return nsmap

    def _merge_namespaces(self, extracted_ns: Dict[str, str]) -> Dict[str, str]:
        """Merge extracted namespaces with config namespaces (config takes priority)."""
        config_ns = self.config.get("namespaces", {})

        # Start with extracted namespaces
        merged = extracted_ns.copy()

        # Override with config namespaces
        merged.update(config_ns)

        if self.debug:
            logger.debug(f"Extracted namespaces: {extracted_ns}")
            logger.debug(f"Config namespaces: {config_ns}")
            logger.debug(f"Merged namespaces: {merged}")

        return merged

    def _apply_filter(
        self, values: List[str], filter_config: Optional[Dict[str, str]]
    ) -> List[str]:
        """Apply filter to list of values based on filter configuration."""
        if not filter_config or not values:
            return values

        filter_type = filter_config.get("type", "").lower()
        pattern = filter_config.get("pattern", "")

        if not pattern:
            logger.warning("Filter specified but no pattern provided")
            return values

        filtered = []
        for value in values:
            if filter_type == "regex":
                if re.search(pattern, value):
                    filtered.append(value)
            elif filter_type == "startswith":
                if value.startswith(pattern):
                    filtered.append(value)
            elif filter_type == "contains":
                if pattern in value:
                    filtered.append(value)
            else:
                logger.warning(f"Unknown filter type: {filter_type}")
                return values

        return filtered

    def _extract_field(
        self, element: etree._Element, field_config: Dict[str, Any], file_path: str
    ) -> Union[str, List[str]]:
        """Extract a single field from an element based on configuration."""
        xpath = field_config.get("xpath", "")
        as_list = field_config.get("as_list", False)
        separator = field_config.get("separator", " | ")
        filter_config = field_config.get("filter")

        if not xpath:
            logger.warning(
                f"No xpath specified for field: {field_config.get('column')}"
            )
            return ""

        try:
            # Execute XPath query
            results = element.xpath(xpath, namespaces=self.namespaces)

            if self.debug and results:
                logger.debug(
                    f"XPath '{xpath}' found {len(results)} result(s) in {file_path}"
                )

            # Convert results to strings
            values = []
            for result in results:
                if isinstance(result, str):
                    values.append(result)
                elif isinstance(result, etree._Element):
                    # If element returned, get its text
                    text = result.text or ""
                    if text.strip():
                        values.append(text.strip())
                elif isinstance(result, etree._ElementUnicodeResult):
                    values.append(str(result))

            # Apply filter if configured
            if filter_config:
                values = self._apply_filter(values, filter_config)

            # Handle missing values
            if not values:
                verbosity = self.config.get("logging", {}).get(
                    "missing_xpath_verbosity", "summary"
                )
                if verbosity in ["summary", "detailed"]:
                    self.stats["fields_missing"] += 1
                    # Track which fields are missing for summary
                    field_name = field_config.get("column", xpath)
                    if field_name not in self.stats["missing_fields_by_name"]:
                        self.stats["missing_fields_by_name"][field_name] = 0
                    self.stats["missing_fields_by_name"][field_name] += 1

                    if verbosity == "detailed":
                        logger.warning(
                            f"XPath '{xpath}' returned no results in {file_path}"
                        )
                return [] if as_list else ""

            # Return as list or joined string based on config
            if as_list:
                return values
            else:
                return separator.join(values)

        except etree.XPathEvalError as e:
            logger.error(f"Invalid XPath expression '{xpath}': {e}")
            self.stats["errors"].append(f"XPath error in {file_path}: {e}")
            return [] if as_list else ""

    def _check_record_filters(self, element: etree._Element, file_path: str) -> bool:
        """Check if record matches all filter conditions.

        Returns True if record should be included, False if it should be filtered out.
        """
        filters = self.config.get("record_filters", [])
        if not filters:
            return True  # No filters means include all records

        for filter_config in filters:
            xpath = filter_config.get("xpath", "")
            condition = filter_config.get("condition", "exists")
            value = filter_config.get("value")

            if not xpath:
                continue

            try:
                # Extract value using XPath
                results = element.xpath(xpath, namespaces=self.namespaces)

                # Convert to text values
                text_values = []
                for result in results:
                    if isinstance(result, str):
                        text_values.append(result)
                    elif hasattr(result, "text") and result.text:
                        text_values.append(result.text)
                    elif isinstance(result, etree._ElementUnicodeResult):
                        text_values.append(str(result))

                # Apply condition
                if condition == "exists":
                    if not text_values:
                        return False
                elif condition == "not_exists":
                    if text_values:
                        return False
                elif condition == "equals" and value is not None:
                    if not any(v == value for v in text_values):
                        return False
                elif condition == "not_equals" and value is not None:
                    if any(v == value for v in text_values):
                        return False
                elif condition == "contains" and value is not None:
                    if not any(value in v for v in text_values):
                        return False
                elif condition == "not_contains" and value is not None:
                    if any(value in v for v in text_values):
                        return False
                elif condition == "matches" and value is not None:
                    # Regex match
                    pattern = re.compile(value)
                    if not any(pattern.search(v) for v in text_values):
                        return False
                elif condition == "not_matches" and value is not None:
                    pattern = re.compile(value)
                    if any(pattern.search(v) for v in text_values):
                        return False
                elif condition == "date_after" and value is not None:
                    # Simple date comparison (works for ISO dates)
                    if not any(v > value for v in text_values):
                        return False
                elif condition == "date_before" and value is not None:
                    if not any(v < value for v in text_values):
                        return False
                elif condition == "in" and isinstance(value, list):
                    if not any(v in value for v in text_values):
                        return False
                elif condition == "not_in" and isinstance(value, list):
                    if any(v in value for v in text_values):
                        return False

            except etree.XPathEvalError as e:
                logger.error(f"Invalid filter XPath '{xpath}': {e}")
                return False

        return True  # All filters passed

    def _process_record(
        self,
        element: etree._Element,
        field_configs: List[Dict[str, Any]],
        file_path: str,
    ) -> Dict[str, Union[str, List[str]]]:
        """Process a single record element and extract all configured fields."""
        record = {}

        # Add filename as first column
        record["_source_file"] = Path(file_path).name

        for field_config in field_configs:
            column_name = field_config.get("column", "")
            value = self._extract_field(element, field_config, file_path)
            record[column_name] = value

        return record

    def _process_file(self, file_path: Path) -> List[Dict[str, Union[str, List[str]]]]:
        """Process a single XML file and extract all records."""
        records = []

        try:
            # Parse XML file
            parser = etree.XMLParser(
                remove_blank_text=True,
                resolve_entities=False,
                recover=True,  # Try to recover from errors
            )
            tree = etree.parse(str(file_path), parser)

            # Extract and merge namespaces
            extracted_ns = self._extract_namespaces(tree)
            self.namespaces = self._merge_namespaces(extracted_ns)

            # Get root xpath for record elements
            root_xpath = self.config.get("root_xpath", "")
            if not root_xpath:
                logger.error("No root_xpath specified in configuration")
                return records

            # Find all record elements
            try:
                record_elements = tree.xpath(root_xpath, namespaces=self.namespaces)
            except etree.XPathEvalError as e:
                logger.error(f"Invalid root_xpath '{root_xpath}': {e}")
                self.stats["errors"].append(f"Root XPath error in {file_path}: {e}")
                return records

            if not record_elements:
                logger.warning(
                    f"No records found with root_xpath '{root_xpath}' in {file_path}"
                )
                return records

            logger.info(f"Found {len(record_elements)} record(s) in {file_path.name}")

            # Process each record
            field_configs = self.config.get("fields", [])
            for idx, element in enumerate(record_elements, 1):
                if self.debug:
                    logger.debug(
                        f"Processing record {idx}/{len(record_elements)} in {file_path.name}"
                    )

                # Check if record passes filters
                if not self._check_record_filters(element, str(file_path)):
                    self.stats["records_filtered"] += 1
                    if self.debug:
                        logger.debug(f"Record {idx} filtered out by record_filters")
                    continue

                record = self._process_record(element, field_configs, str(file_path))
                records.append(record)
                self.stats["records_extracted"] += 1

            self.stats["files_processed"] += 1

        except etree.XMLSyntaxError as e:
            logger.error(f"Invalid XML in {file_path}: {e}")
            self.stats["files_skipped"] += 1
            self.stats["errors"].append(f"XML syntax error in {file_path}: {e}")

            if not self.config.get("logging", {}).get("skip_invalid_xml", True):
                raise

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            self.stats["files_skipped"] += 1
            self.stats["errors"].append(f"Error in {file_path}: {e}")
            raise

        return records

    def extract(
        self, input_dir: Path, output_file: Path, output_format: str = "csv"
    ) -> None:
        """Main extraction method - processes all XML files and writes output."""
        # Find all XML files
        xml_files = list(input_dir.glob("*.xml"))

        if not xml_files:
            console.print(f"[yellow]No XML files found in {input_dir}[/yellow]")
            return

        console.print(f"[cyan]Found {len(xml_files)} XML file(s) to process[/cyan]")

        all_records = []

        # Process files with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Processing XML files...", total=len(xml_files)
            )

            for xml_file in xml_files:
                progress.update(
                    task, description=f"[cyan]Processing {xml_file.name}..."
                )
                records = self._process_file(xml_file)
                all_records.extend(records)
                progress.advance(task)

        # Write output
        if all_records:
            self._write_output(all_records, output_file, output_format)
            console.print(
                f"\n[green]✓ Successfully wrote extracted data from {len(all_records)} record(s) to {output_file.absolute()}[/green]"
            )
        else:
            console.print(
                "\n[yellow]⚠ No records extracted, output not created[/yellow]"
            )

        # Print missing fields summary if verbosity is summary or detailed
        verbosity = self.config.get("logging", {}).get(
            "missing_xpath_verbosity", "summary"
        )
        if (
            verbosity in ["summary", "detailed"]
            and self.stats["missing_fields_by_name"]
        ):
            console.print("\n[yellow]Missing Fields Summary:[/yellow]")
            for field_name, count in sorted(
                self.stats["missing_fields_by_name"].items()
            ):
                console.print(f"  [yellow]• {field_name}: {count} record(s)[/yellow]")

        # Print statistics
        self._print_statistics()

    def _write_output(
        self,
        records: List[Dict[str, Union[str, List[str]]]],
        output_file: Path,
        output_format: str,
    ) -> None:
        """Write extracted records to file using pandas."""
        if not records:
            return

        # Create DataFrame
        df = pd.DataFrame(records)

        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write based on format
        if output_format == "csv":
            # For CSV, convert lists to pipe-separated strings for compatibility
            df_csv = df.copy()
            for col in df_csv.columns:
                if df_csv[col].apply(lambda x: isinstance(x, list)).any():
                    df_csv[col] = df_csv[col].apply(
                        lambda x: " | ".join(x) if isinstance(x, list) else x
                    )
            df_csv.to_csv(output_file, index=False, encoding="utf-8")
            logger.info(f"Wrote {len(records)} records to CSV: {output_file}")

        elif output_format == "parquet":
            # Parquet supports native lists
            df.to_parquet(output_file, index=False, engine="pyarrow")
            logger.info(f"Wrote {len(records)} records to Parquet: {output_file}")

        elif output_format == "excel":
            # Excel: convert lists to strings
            df_excel = df.copy()
            for col in df_excel.columns:
                if df_excel[col].apply(lambda x: isinstance(x, list)).any():
                    df_excel[col] = df_excel[col].apply(
                        lambda x: " | ".join(x) if isinstance(x, list) else x
                    )
            df_excel.to_excel(output_file, index=False, engine="openpyxl")
            logger.info(f"Wrote {len(records)} records to Excel: {output_file}")

        elif output_format == "json":
            # JSON supports native lists
            df.to_json(output_file, orient="records", indent=2, force_ascii=False)
            logger.info(f"Wrote {len(records)} records to JSON: {output_file}")

        else:
            raise ValueError(f"Unsupported output format: {output_format}")

    def _print_statistics(self) -> None:
        """Print extraction statistics in a nice table."""
        table = Table(
            title="Extraction Statistics", show_header=True, header_style="bold magenta"
        )
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="green", justify="right")

        table.add_row("Files processed", str(self.stats["files_processed"]))
        table.add_row("Files skipped", str(self.stats["files_skipped"]))
        table.add_row("Records extracted", str(self.stats["records_extracted"]))
        if self.stats["records_filtered"] > 0:
            table.add_row("Records filtered out", str(self.stats["records_filtered"]))
        table.add_row("Fields with missing data", str(self.stats["fields_missing"]))
        table.add_row("Errors", str(len(self.stats["errors"])))

        console.print()
        console.print(table)

        if self.stats["errors"] and self.debug:
            console.print("\n[red]Errors encountered:[/red]")
            for error in self.stats["errors"][:10]:  # Show first 10 errors
                console.print(f"  • {error}")
            if len(self.stats["errors"]) > 10:
                console.print(f"  ... and {len(self.stats['errors']) - 10} more")


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load and validate configuration from YAML file."""
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Validate required fields
    required_fields = ["root_xpath", "fields"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Required field '{field}' missing in configuration")

    if not config["fields"]:
        raise ValueError("No fields configured for extraction")

    return config


@click.command()
@click.argument(
    "config",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--input",
    "-i",
    "input_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Input directory containing XML files (overrides config)",
)
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(path_type=Path),
    help="Output file path (overrides config)",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["csv", "parquet", "excel", "json"], case_sensitive=False),
    default="csv",
    help="Output format (default: csv)",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug mode with verbose logging",
)
def main(
    config: Path,
    input_dir: Optional[Path],
    output_file: Optional[Path],
    output_format: str,
    debug: bool,
):
    """
    XML Field Extractor - Extract fields from XML files to CSV/Parquet/Excel/JSON

    CONFIG: Path to configuration YAML file (required)

    Supports complex XML formats (Dublin Core, METS, LIDO, PREMIS, etc.)
    with flexible XPath-based field extraction and filtering.

    Output formats: CSV, Parquet (with native list support), Excel, JSON
    """
    # Print banner
    console.print()
    console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]   XML Field Extractor[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]")
    console.print()

    try:
        # Load configuration
        console.print(f"[cyan]Loading configuration from {config}...[/cyan]")
        cfg = load_config(config)

        # Override with command-line arguments
        if input_dir:
            cfg["input_directory"] = str(input_dir)
        if output_file:
            cfg["output_file"] = str(output_file)

        # Get output path and add extension based on format
        output_base = Path(cfg.get("output_file", "output"))

        # Map format to file extension
        format_extensions = {
            "csv": ".csv",
            "parquet": ".parquet",
            "excel": ".xlsx",
            "json": ".json",
        }

        # Add extension if not present
        extension = format_extensions.get(output_format, ".csv")
        if output_base.suffix not in format_extensions.values():
            output_path = output_base.with_suffix(extension)
        else:
            output_path = output_base

        # Setup logging - always create log file next to output file
        log_path = output_path.parent / f"{output_path.stem}.log"

        # Remove default logger
        logger.remove()

        # Add console logger (only warnings and errors if not debug)
        logger.add(
            lambda msg: console.print(msg, end=""),
            level="DEBUG" if debug else "WARNING",
            format="<level>{message}</level>",
        )

        # Add file logger
        logger.add(
            log_path,
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            rotation="10 MB",
        )

        logger.info("=" * 50)
        logger.info("XML Field Extractor - Starting extraction")
        logger.info(f"Configuration: {config}")
        logger.info(f"Debug mode: {debug}")

        # Get input/output paths
        input_path = Path(cfg.get("input_directory", "./example_data"))

        if not input_path.exists():
            console.print(f"[red]✗ Input directory not found: {input_path}[/red]")
            return

        console.print(f"[cyan]Input directory: {input_path}[/cyan]")
        console.print(f"[cyan]Output file: {output_path}[/cyan]")
        console.print(f"[cyan]Output format: {output_format.upper()}[/cyan]")
        console.print(f"[cyan]Log file: {log_path}[/cyan]")
        console.print()

        # Create extractor and run
        extractor = XMLExtractor(cfg, debug=debug)
        extractor.extract(input_path, output_path, output_format)

        logger.info("Extraction completed successfully")
        console.print("\n[green]✓ Extraction completed![/green]")

    except Exception as e:
        logger.exception("Fatal error during extraction")
        console.print(f"\n[red]✗ Error: {e}[/red]")
        raise click.Abort()


if __name__ == "__main__":
    main()
