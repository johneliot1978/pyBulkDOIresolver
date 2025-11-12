# pyBulkDOIresolver

A Python script for bulk resolving Digital Object Identifiers (DOIs) to fetch publication metadata using the Crossref API. This tool is designed to be robust, handling API rate limits, network errors, and providing resume functionality for interrupted jobs.

## Features

- **Bulk DOI Resolution**: Process a list of DOIs from an input file and retrieve their metadata.
- **Robust Error Handling**: Includes a retry/backoff mechanism to handle Crossref API rate limits (429 Too Many Requests, 503 Service Unavailable).
- **Resume Functionality**: If the script is interrupted, you can resume from the last successfully processed batch, avoiding redundant requests.
- **Efficient Batching**: Sends DOIs in batches to the Crossref API for efficient processing.
- **Configurable**: Set your email address for the Crossref API's "mailto" parameter via an environment file.
- **Tab-Separated Output**: Saves the resolved metadata in a clear and easy-to-parse TSV (Tab-Separated Values) file.

## Functionality

The script reads a list of DOIs from a specified input file. It then sends these DOIs in batches to the Crossref API. For each DOI, it attempts to fetch metadata such as:

- DOI
- Title
- Authors
- Journal Title
- ISSN
- Volume
- Issue
- Pages

The script handles cases where a DOI cannot be resolved, leaving the metadata fields blank in the output file for those entries. Progress is saved to a `.inProgress` file, which allows the script to resume from where it left off.

## Usage

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/pyBulkDOIresolver.git
    cd pyBulkDOIresolver
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: You will need to create a `requirements.txt` file with the content `python-dotenv` and `requests`)*

3.  **Create an environment file:**
    Copy the `example.env` to `.env` and update the `CROSSREF_EMAIL` with your email address. This is good practice when using the Crossref API.
    ```bash
    cp example.env .env
    ```

4.  **Prepare your input file:**
    Create a text file (e.g., `dois.txt`) with one DOI per line. The DOI can be a plain DOI or a full URL.

5.  **Run the script:**
    ```bash
    python pyBulkDOIresolver.py <your_input_file.txt> [batch_size]
    ```
    -   `<your_input_file.txt>`: The path to your file containing DOIs.
    -   `[batch_size]`: (Optional) The number of DOIs to send in each batch. Defaults to 45.

    **Example:**
    ```bash
    python pyBulkDOIresolver.py testDois.txt 50
    ```

6.  **Resuming an interrupted job:**
    If the script is interrupted, you can use the `--resume` flag to continue from where it left off.
    ```bash
    python pyBulkDOIresolver.py your_input_file.txt --resume
    ```

## API Limit Guardrails

The Crossref API has a rate limit to ensure fair usage. This script respects these limits by:

-   **Backing off on rate limit errors**: If a `429 Too Many Requests` or `503 Service Unavailable` status code is received, the script will pause for 10 seconds before retrying the batch.
-   **Configurable Batch Size**: While the default batch size is 45, you can adjust this as a command-line argument. The Crossref API documentation suggests a maximum of 50 DOIs per filter.

It is highly recommended to set your email in the `.env` file, as this makes you a "polite" user of the Crossref API and can sometimes result in better service.

## Output

The script generates a file named `resolved_metadata.tsv` in the same directory. This file is a tab-separated values file with the following columns:

-   `DOI`
-   `Title`
-   `Authors`
-   `Journal`
-   `ISSN`
-   `Volume`
-   `Issue`
-   `Pages`
