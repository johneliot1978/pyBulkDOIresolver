# pyBulkDOIresolver

A Python script to bulk resolve Digital Object Identifiers (DOIs) from a CSV file and enrich it with metadata from the Crossref API.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Error Handling](#error-handling)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Bulk DOI Resolution**: Processes a CSV file to resolve DOIs in bulk.
- **Metadata Enrichment**: Appends metadata (Title, Authors, Journal, ISSN, Volume, Issue, Pages) to the CSV.
- **Resumable**: Can resume interrupted jobs.
- **Batch Processing**: Efficiently handles large numbers of DOIs by batching requests to the Crossref API.
- **Malformed DOI Handling**: Isolates and logs malformed DOIs without halting the entire process.
- **Safe CSV Writing**: Uses a temporary file to prevent data corruption.
- **URL Cleaning**: Automatically cleans and resolves DOIs from URLs, including those with prefixes like OpenAthens.

## Prerequisites

- Python 3.6 or higher
- Pip (Python package installer)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/pyBulkDOIresolver.git
   cd pyBulkDOIresolver
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

The script is run from the command line with the following arguments:

```bash
python pyBulkDOIresolver.py <input_file> <doi_column> <output_start_column> [options]
```

### Arguments

- `input_file`: The input CSV file to process.
- `doi_column`: The Excel-style column letter containing DOI URLs (e.g., 'G').
- `output_start_column`: The Excel-style column letter where resolved data should start (e.g., 'J').

### Options

- `--batch_size <size>`: DOIs per batch request (default: 45).
- `--resume`: Resume an interrupted job.
- `--wait_time <seconds>`: Time in seconds to wait between each batch request (default: 1.0).

### Example

```bash
python pyBulkDOIresolver.py my_dois.csv G J --batch_size 50
```

## Configuration

The script uses a `.env` file to manage configuration.

1. **Create a `.env` file** by copying the example file:
   ```bash
   cp example.env .env
   ```

2. **Edit the `.env` file** to set your email address for the Crossref API:
   ```env
   CROSSREF_EMAIL=your.email@example.com
   ```
   This is important for good API etiquette and allows Crossref to contact you if there are any issues.

## Error Handling

- **Malformed DOIs**: If a batch request fails due to a malformed DOI, the script will recursively split the batch to isolate and log the problematic DOI in `malformed_dois.log`.
- **Network Errors**: The script will retry network requests up to 3 times before skipping a batch.
- **File Safety**: The script writes to a temporary file and replaces the original only upon successful completion of a batch, preventing data loss.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
