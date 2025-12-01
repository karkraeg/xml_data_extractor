# XML Field Extractor

A flexible, configurable Python tool for extracting fields from XML files and converting them to rectangular data formats like CSV or Excel. Designed to handle complex XML formats like **METS**, **LIDO**, **PREMIS**, and more.

## Disclaimer

🚨 This project was completely developed with the assistance of GitHub Copilot.
It is currently in a prototype stage — use at your own risk. Contributions, reviews, and testing are highly appreciated.

## ✨ Features

- 🔍 **Flexible XPath-based extraction** - Extract any field using XPath expressions
- 🏷️ **Automatic namespace detection** - No need to manually define namespaces (but you can if needed)
- 🎯 **Advanced filtering** - Filter extracted values using regex, startswith, or contains patterns
- 🔬 **Record filtering** - Pre-filter records before extraction based on any field criteria (dates, licenses, etc.)
- 📊 **Multiple value handling** - Concatenate multiple values with custom separators
- 🚀 **Batch processing** - Process entire directories of XML files
- 📈 **Progress tracking** - Beautiful progress bars and statistics with Rich
- 📝 **Comprehensive logging** - Detailed logs with Loguru
- 🛡️ **Error resilience** - Skip invalid XML files and continue processing
- 🎨 **Modern CLI** - Built with Click for an intuitive command-line interface

## 📦 Installation

This project uses [uv](https://github.com/astral-sh/uv) for fast, reliable package management.

```bash
# Clone the repository
git clone <your-repo-url>
cd xml_extractor

# Install dependencies with uv
uv sync
```

## 🚀 Quick Start

1. **Prepare your XML files** - Place them in a directory (e.g., `./example_data`)

2. **Configure extraction** - Edit `config.yaml` to define:
   - Root XPath for record elements
   - Field mappings with XPath expressions
   - Namespaces (optional - auto-detected if omitted)
   - Filters for specific values

3. **Run extraction**:
```bash
uv run python xml_extractor.py
```

## 📖 Configuration

### Basic Configuration Structure

```yaml
# Input/Output
input_directory: "./example_data"
output_file: "output.csv"

# XPath to root element (each match = one CSV row)
root_xpath: ".//oai_dc:dc"

# Namespace definitions (optional)
namespaces:
  oai_dc: "http://www.openarchives.org/OAI/2.0/oai_dc/"
  dc: "http://purl.org/dc/elements/1.1/"

# Field mappings
fields:
  - column: "Title"
    xpath: ".//dc:title/text()"
  
  - column: "Creators"
    xpath: ".//dc:creator/text()"
    separator: " | "  # For multiple values
  
  - column: "URN"
    xpath: ".//dc:identifier/text()"
    filter:
      type: "startswith"
      pattern: "urn:nbn"
```

### Field Configuration Options

Each field can have the following properties:

| Property    | Required | Description                                       |
|-------------|----------|---------------------------------------------------|
| `column`    | ✅ Yes    | Name of the CSV column                            |
| `xpath`     | ✅ Yes    | XPath expression (relative to root_xpath)         |
| `separator` | ❌ No     | Separator for multiple values (default: `" \| "`) |
| `filter`    | ❌ No     | Filter configuration for value selection          |

### Filter Types

Apply filters to select specific values when an XPath matches multiple elements:

**Regex Filter:**
```yaml
filter:
  type: "regex"
  pattern: "^urn:nbn"  # Matches URNs starting with "urn:nbn"
```

**StartsWith Filter:**
```yaml
filter:
  type: "startswith"
  pattern: "10."  # Matches DOIs starting with "10."
```

**Contains Filter:**
```yaml
filter:
  type: "contains"
  pattern: "miami.uni-muenster.de"  # Matches URLs containing this domain
```

### Transform

Extract specific parts from text using regex patterns with capture groups:

```yaml
# Extract date from MARC 008 field and reformat: "180830e20180830||..." → "2018-08-30"
- column: "Publication_Date"
  xpath: ".//marcxml:controlfield[@tag='008']/text()"
  transform:
    regex: "\\d{6}e(\\d{4})(\\d{2})(\\d{2})"
    format: "{0}-{1}-{2}"  # Reformat using capture groups

# Extract language code: "...ger||||||" → "ger"
- column: "Language_Code"
  xpath: ".//marcxml:controlfield[@tag='008']/text()"
  transform:
    regex: "([a-z]{3})\\|{6}$"
    group: 1
```

**Transform options:**
- `regex`: Regular expression pattern (use `\\` for backslashes in YAML)
- `group`: Which capture group to extract (default: 0 = full match, 1+ = capture groups)
- `format`: Optional format string to reformat the matched data
  - Use `{0}`, `{1}`, `{2}` to reference capture groups
  - Example: `"{0}-{1}-{2}"` converts `20180830` to `2018-08-30`

### URL Prefix

Automatically prepend a URL to extracted values:

```yaml
- column: "DOI"
  xpath: ".//datafield[@tag='024']/subfield[@code='a']/text()"
  url_prefix: "https://doi.org/"  # Converts "10.1234/..." to "https://doi.org/10.1234/..."
```

### Record Filters

Pre-filter records **before** extraction to only process records matching specific criteria:

```yaml
# Only extract records from the 1920s with Public Domain licenses
record_filters:
  - xpath: ".//mods:dateCreated/text()"
    condition: "matches"
    value: "192\\d"
  
```

### Record Filters

Pre-filter records **before** extraction to only process records matching specific criteria:

```yaml
# Only extract records from the 1920s with Public Domain licenses
record_filters:
  - xpath: ".//mods:dateCreated/text()"
    condition: "matches"
    value: "192\\d"
  
  - xpath: ".//mods:accessCondition/text()"
    condition: "contains"
    value: "publicdomain"
```

**Available filter conditions:** `exists`, `not_exists`, `equals`, `not_equals`, `contains`, `not_contains`, `matches`, `not_matches`, `date_after`, `date_before`, `in`, `not_in`

📖 **See [RECORD_FILTERS.md](RECORD_FILTERS.md) for complete documentation and examples**

## 🎯 Usage Examples

### Basic Usage
```bash
# Use default config.yaml
uv run python xml_extractor.py

# Specify custom config
uv run python xml_extractor.py --config my_config.yaml

# Override input/output
uv run python xml_extractor.py --input ./my_xmls --output results.csv

# Enable debug mode
uv run python xml_extractor.py --debug
```

### Command-Line Options

```
Options:
  -c, --config PATH       Path to configuration YAML file [default: config.yaml]
  -i, --input PATH        Input directory containing XML files (overrides config)
  -o, --output PATH       Output CSV file path (overrides config)
  --debug                 Enable debug mode with verbose logging
  --log-file PATH         Log file path (overrides config)
  --help                  Show this message and exit
```

## 📂 Example: Dublin Core OAI-PMH Records

### Input XML Structure

Your XML files can have different structures:

**Single record per file:**
```xml
<OAI-PMH xmlns="...">
  <GetRecord>
    <record>
      <metadata>
        <oai_dc:dc xmlns:oai_dc="..." xmlns:dc="...">
          <dc:title>My Title</dc:title>
          <dc:creator>Author Name</dc:creator>
          <!-- more fields -->
        </oai_dc:dc>
      </metadata>
    </record>
  </GetRecord>
</OAI-PMH>
```

**Multiple records per file:**
```xml
<records>
  <record>
    <metadata>
      <oai_dc:dc xmlns:oai_dc="..." xmlns:dc="...">
        <!-- fields -->
      </oai_dc:dc>
    </metadata>
  </record>
  <record>
    <metadata>
      <oai_dc:dc xmlns:oai_dc="..." xmlns:dc="...">
        <!-- fields -->
      </oai_dc:dc>
    </metadata>
  </record>
</records>
```

Both formats work seamlessly - the tool finds all `oai_dc:dc` elements across all files.

### Output CSV

```csv
Title,Creators,Date,URN,DocType
"Religiöse Traditionen in...","Dam, P. (Peter) van",2018-08-30,urn:nbn:de:hbz:6-87159515859,doc-type:article
"Urinary Dickkopf 3...","Jehn, U. (Ulrich) | Altuner, U. (Ugur)",2024-08-21,urn:nbn:de:hbz:6-05978733071,doc-type:article
```

## 🔧 Advanced Examples

### METS Configuration

```yaml
root_xpath: ".//mets:mets"

namespaces:
  mets: "http://www.loc.gov/METS/"
  mods: "http://www.loc.gov/mods/v3"
  xlink: "http://www.w3.org/1999/xlink"

fields:
  - column: "Title"
    xpath: ".//mets:dmdSec/mets:mdWrap/mets:xmlData/mods:mods/mods:titleInfo/mods:title/text()"
  
  - column: "FileID"
    xpath: ".//mets:file/@ID"
```

### LIDO Configuration

```yaml
root_xpath: ".//lido:lido"

namespaces:
  lido: "http://www.lido-schema.org"

fields:
  - column: "ObjectTitle"
    xpath: ".//lido:titleWrap/lido:titleSet/lido:appellationValue/text()"
  
  - column: "ObjectType"
    xpath: ".//lido:objectWorkType/lido:term/text()"
```

## 📊 Statistics & Logging

After extraction, you'll see:

- ✅ Files processed
- ⚠️ Files skipped (due to errors)
- 📝 Total records extracted
- ⚠️ Fields with missing data
- ❌ Errors encountered

All details are logged to `extraction.log` (configurable).

## 🛠️ Development

### Project Structure

```
xml_extractor/
├── xml_extractor.py      # Main application
├── config.yaml           # Configuration file
├── pyproject.toml        # Project dependencies
├── README.md             # This file
└── extraction.log        # Generated log file
```

### Dependencies

- **lxml** - Fast XML processing with XPath support
- **rich** - Beautiful terminal output
- **click** - CLI framework
- **loguru** - Simple, powerful logging
- **pyyaml** - YAML configuration parsing

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## 📄 License

MIT License - feel free to use this tool for your projects!

## 💡 Tips

1. **Start with debug mode** (`--debug`) when creating a new configuration to see what's happening
2. **Test with a small subset** of files first before processing large batches
3. **Use filters** to extract specific identifiers (URNs, DOIs, etc.) from multi-value fields
4. **Check the log file** (`extraction.log`) for warnings about missing XPath matches
5. **Namespaces are auto-detected** - you only need to define them manually if auto-detection fails

## 🆘 Troubleshooting

### "No records found with root_xpath"
- Check your `root_xpath` expression
- Verify namespace prefixes match your XML
- Try without namespace prefix: `.//dc` instead of `.//oai_dc:dc`

### "Invalid XPath expression"
- Ensure XPath syntax is correct
- Check that namespace prefixes are defined
- Use `.//` for descendant search, `/` for direct children

### "XML syntax error"
- Enable `skip_invalid_xml: true` in config to skip bad files
- Check XML file encoding (should be UTF-8)
- Validate XML structure with an XML validator

