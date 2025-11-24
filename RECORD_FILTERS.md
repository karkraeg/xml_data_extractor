# Record Filtering Guide

## Overview

Record filters allow you to pre-filter XML records **before** extraction. Only records that match ALL specified filter conditions will be processed and included in the output.

## Basic Structure

```yaml
record_filters:
  - xpath: ".//path/to/field/text()"
    condition: "exists"
    value: "optional_value"  # Required for some conditions
```

## Filter Conditions

### Existence Checks

**`exists`** - Field must have a value
```yaml
- xpath: ".//mods:title/text()"
  condition: "exists"
```

**`not_exists`** - Field must NOT have a value
```yaml
- xpath: ".//mods:abstract/text()"
  condition: "not_exists"
```

### Exact Matching

**`equals`** - Field must exactly match the value
```yaml
- xpath: ".//mods:language/text()"
  condition: "equals"
  value: "eng"
```

**`not_equals`** - Field must NOT match the value
```yaml
- xpath: ".//mods:type/text()"
  condition: "not_equals"
  value: "collection"
```

### Substring Matching

**`contains`** - Field must contain the substring
```yaml
- xpath: ".//mods:accessCondition/text()"
  condition: "contains"
  value: "publicdomain"
```

**`not_contains`** - Field must NOT contain the substring
```yaml
- xpath: ".//mods:rights/text()"
  condition: "not_contains"
  value: "restricted"
```

### Regular Expression Matching

**`matches`** - Field must match the regex pattern
```yaml
# Only records from the 1920s
- xpath: ".//mods:dateCreated/text()"
  condition: "matches"
  value: "192\\d"
```

**`not_matches`** - Field must NOT match the regex pattern
```yaml
# Exclude draft versions
- xpath: ".//mods:title/text()"
  condition: "not_matches"
  value: "\\[DRAFT\\]"
```

### Date Comparisons

**`date_after`** - Field value must be after the specified date (string comparison)
```yaml
# Only records from 2020 onwards
- xpath: ".//mods:dateCreated/text()"
  condition: "date_after"
  value: "2020"
```

**`date_before`** - Field value must be before the specified date
```yaml
# Only historical records before 1900
- xpath: ".//mods:dateCreated/text()"
  condition: "date_before"
  value: "1900"
```

### List Membership

**`in`** - Field value must be in the list
```yaml
# Only specific languages
- xpath: ".//mods:language/text()"
  condition: "in"
  value: ["eng", "deu", "fra"]
```

**`not_in`** - Field value must NOT be in the list
```yaml
# Exclude certain types
- xpath: ".//mods:type/text()"
  condition: "not_in"
  value: ["collection", "index", "series"]
```

## Complete Examples

### Example 1: Filter by License

Only extract records with Creative Commons licenses:

```yaml
record_filters:
  - xpath: ".//mods:accessCondition[@type='use and reproduction']/text()"
    condition: "contains"
    value: "creativecommons.org"
```

### Example 2: Filter by Date Range

Only extract records from 1920-1929:

```yaml
record_filters:
  - xpath: ".//mods:dateCreated/text()"
    condition: "date_after"
    value: "1919"
  
  - xpath: ".//mods:dateCreated/text()"
    condition: "date_before"
    value: "1930"
```

### Example 3: Multiple Conditions (AND logic)

Only extract English-language books with abstracts:

```yaml
record_filters:
  # Must be English
  - xpath: ".//mods:language/text()"
    condition: "equals"
    value: "eng"
  
  # Must have an abstract
  - xpath: ".//mods:abstract/text()"
    condition: "exists"
  
  # Must be a book (not collection, series, etc.)
  - xpath: ".//mods:typeOfResource/text()"
    condition: "equals"
    value: "text"
```

### Example 4: Exclude Records

Exclude records without proper metadata:

```yaml
record_filters:
  # Must have a title
  - xpath: ".//mods:title/text()"
    condition: "exists"
  
  # Must have a date
  - xpath: ".//mods:dateCreated/text()"
    condition: "exists"
  
  # Exclude drafts
  - xpath: ".//mods:note/text()"
    condition: "not_contains"
    value: "DRAFT"
```

### Example 5: Complex License Filtering

Only Public Domain or CC0 licensed items:

```yaml
record_filters:
  - xpath: ".//mods:accessCondition[@type='use and reproduction']/text()"
    condition: "matches"
    value: "(publicdomain|cc0)"
```

## Tips

1. **All filters must match** - Record filters use AND logic. A record must satisfy ALL conditions to be included.

2. **XPath is relative to root_xpath** - Filter XPath expressions are evaluated relative to the element matched by `root_xpath`.

3. **Check statistics** - The extraction statistics show "Records filtered out" so you can verify your filters are working as expected.

4. **Test with --debug** - Use the `--debug` flag to see which records are being filtered out.

5. **Use regex for complex patterns** - The `matches` condition supports full regex patterns for complex filtering.

6. **String comparison for dates** - Date comparisons use simple string comparison, so use consistent date formats (ISO 8601 recommended).

## Performance Note

Record filtering happens early in the processing pipeline, before field extraction. This means filtered records are skipped entirely, improving performance when you only need a subset of records.
