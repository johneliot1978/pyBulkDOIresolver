import os
import argparse
import requests
import json
import time
import sys
import math
import re
from datetime import datetime
from dotenv import load_dotenv
import csv
from urllib.parse import unquote # <-- Import the unquote function

# --- Configuration ---
load_dotenv()
CROSSREF_EMAIL = os.getenv("CROSSREF_EMAIL", "anonymous@example.com")
CROSSREF_API_URL = "https://api.crossref.org/works"
PROGRESS_FILE = ".inProgress"
DEFAULT_BATCH_SIZE = 45
MALFORMED_LOG_FILENAME = "malformed_dois.log"

# --- Helper Functions ---

def format_time(seconds):
    """Formats seconds into a human-readable HH:MM:SS string."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def col_to_index(col_name):
    """Converts an Excel-style column name (A, B, AA) to a zero-based index."""
    if not isinstance(col_name, str) or not col_name.isalpha():
        raise ValueError("Column name must be a string of letters.")
    index = 0
    for char in col_name.upper():
        index = index * 26 + (ord(char) - ord('A') + 1)
    return index - 1

def write_csv_safely(filename, header, data_rows):
    """Writes data to a temporary file and then replaces the original."""
    temp_filename = filename + ".tmp"
    try:
        with open(temp_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(data_rows)
        os.replace(temp_filename, filename)
    except Exception as e:
        print(f"\nCRITICAL ERROR: Failed to write update to CSV file: {e}", file=sys.stderr)
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

# --- Main Script Logic ---

def get_metadata_in_batch(dois, malformed_log_file):
    """
    Sends a bulk GET request. If a 400 Bad Request error occurs, it recursively
    splits the batch to isolate and skip the malformed DOI.
    """
    headers = {'User-Agent': f'DOIResolver/1.0 (mailto:{CROSSREF_EMAIL})'}
    valid_dois = [doi for doi in dois if doi]
    if not valid_dois:
        return []

    filter_string = ','.join([f"doi:{doi}" for doi in valid_dois])
    params = {'filter': filter_string}
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = requests.get(CROSSREF_API_URL, headers=headers, params=params)
            if response.status_code in [429, 503]:
                print(f"\n  - Received status {response.status_code}. Backing off for 10 seconds...", file=sys.stderr)
                time.sleep(10)
                continue
            response.raise_for_status()
            results = response.json()
            return results.get('message', {}).get('items', [])
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                sys.stdout.write('\r' + " " * 90 + '\r')
                print(f"\n  - Received 400 Bad Request. A DOI in this batch is malformed. Isolating it...", file=sys.stderr)
                if len(valid_dois) == 1:
                    bad_doi = valid_dois[0]
                    timestamp = datetime.now().isoformat()
                    print(f"  - Isolated problematic DOI: {bad_doi}", file=sys.stderr)
                    malformed_log_file.write(f"[{timestamp}] Skipped DOI: {bad_doi}\n")
                    malformed_log_file.flush()
                    return []
                else:
                    mid_point = len(valid_dois) // 2
                    first_half = valid_dois[:mid_point]
                    second_half = valid_dois[mid_point:]
                    
                    results1 = get_metadata_in_batch(first_half, malformed_log_file)
                    results2 = get_metadata_in_batch(second_half, malformed_log_file)
                    return results1 + results2
            print(f"\n  - Unrecoverable HTTP Error for this batch: {e}", file=sys.stderr)
            return []
        except requests.exceptions.RequestException as e:
            print(f"\n  - A network error occurred: {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                print("  - Retrying after a short delay...", file=sys.stderr)
                time.sleep(2)
            continue
    print(f"\n  - Batch failed after {max_retries} attempts. Skipping.", file=sys.stderr)
    return []


def save_progress(filename, index):
    """Saves the current progress."""
    with open(PROGRESS_FILE, 'w') as f:
        f.write(f"{filename}\n{index}")

def load_progress():
    """Loads progress. Returns (filename, index)."""
    if not os.path.exists(PROGRESS_FILE): return None, 0
    try:
        with open(PROGRESS_FILE, 'r') as f:
            return f.readline().strip(), int(f.readline().strip())
    except (ValueError, IndexError):
        return None, 0

def clear_progress():
    """Removes the progress file."""
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

def parse_metadata(item):
    """Parses the JSON response for a single DOI."""
    if not item: return {}
    doi = item.get('DOI', '')
    title = ''.join(item.get('title', ['']))
    authors = []
    if 'author' in item and isinstance(item['author'], list):
        for author in item['author']:
            if isinstance(author, dict):
                given, family = author.get('given', ''), author.get('family', '')
                author_name = f"{given} {family}".strip()
                if author_name: authors.append(author_name)
    journal = ''.join(item.get('container-title', ['']))
    issn = ', '.join(item.get('ISSN', [])) if isinstance(item.get('ISSN'), list) else ""
    return {'DOI': doi, 'Title': title, 'Authors': '; '.join(authors), 'Journal': journal,
            'ISSN': issn, 'Volume': item.get('volume', ''), 'Issue': item.get('issue', ''),
            'Pages': item.get('page', '')}

def main():
    parser = argparse.ArgumentParser(description="Bulk resolve DOIs within a CSV file and write the results back into the same file.")
    parser.add_argument("input_file", help="The input CSV file to process.")
    parser.add_argument("doi_column", help="The Excel-style column letter containing DOI URLs (e.g., 'G').")
    parser.add_argument("output_start_column", help="The Excel-style column letter where resolved data should start (e.g., 'J').")
    parser.add_argument("--batch_size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"DOIs per batch request (default: {DEFAULT_BATCH_SIZE}).")
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted job.")
    parser.add_argument("--wait_time", type=float, default=1.0, 
                        help="Time in seconds to wait between each batch request (default: 1.0).")
    args = parser.parse_args()

    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            all_rows = list(reader)
            if not all_rows:
                print("Error: The CSV file is empty.", file=sys.stderr)
                return
            header = all_rows[0]
            data_rows = all_rows[1:]

    except FileNotFoundError:
        print(f"Error: The file '{args.input_file}' was not found.", file=sys.stderr)
        return
    except Exception as e:
        print(f"Error reading CSV file: {e}", file=sys.stderr)
        return

    try:
        doi_col_index = col_to_index(args.doi_column)
        output_start_index = col_to_index(args.output_start_column)
    except ValueError as e:
        print(f"Error: Invalid column specified. {e}", file=sys.stderr)
        return

    if doi_col_index >= len(header):
        print(f"Error: DOI column '{args.doi_column}' is out of bounds for the CSV file.", file=sys.stderr)
        return

    doi_pattern = re.compile(r'(10\.[0-9.]+/\S*[A-Za-z0-9])')
    
    print("Screening input file for valid DOI formats...")
    skipped_line_count = 0
    dois = []
    
    # --- MODIFICATION: Define the redirector prefix ---
    openathens_prefix = "https://go.openathens.net/redirector/acu.edu.au?url="

    for row in data_rows:
        try:
            cell_content = row[doi_col_index]
            
            # --- MODIFICATION: Check for and clean the prefix before searching for a DOI ---
            if cell_content.startswith(openathens_prefix):
                encoded_part = cell_content[len(openathens_prefix):]
                cell_content = unquote(encoded_part)
            
            match = doi_pattern.search(cell_content)
            if match:
                cleaned_doi = match.group(1).rstrip('. ,)') # Clean trailing characters
                dois.append(cleaned_doi)
            else:
                if cell_content.strip(): skipped_line_count += 1
                dois.append(None)
        except IndexError:
            dois.append(None)
    
    if skipped_line_count > 0:
        print(f"  - Skipped {skipped_line_count} rows where the specified column did not contain a valid DOI format.")
    print("Screening complete.")

    if not any(dois):
        print("No valid DOIs found in the specified column.")
        return

    total_dois = len(dois)
    total_batches = math.ceil(total_dois / args.batch_size)
    print("-" * 50)
    print("Job Summary:")
    print(f"  - Input file:         {args.input_file}")
    print(f"  - Total data rows:    {len(data_rows)}")
    print(f"  - DOI column:         {args.doi_column} (index {doi_col_index})")
    print(f"  - Output start column:{args.output_start_column} (index {output_start_index})")
    print(f"  - Batch size:         {args.batch_size}")
    print(f"  - Wait time:          {args.wait_time}s")
    print(f"  - Total batches:      {total_batches}")
    print("-" * 50)

    start_index = 0
    if args.resume:
        saved_filename, saved_index = load_progress()
        if saved_filename == args.input_file and saved_index > 0:
            start_index = saved_index
            print(f"Resuming job from row number {start_index + 2} (data row {start_index + 1}).\n")
        else:
            print("Warning: --resume specified, but no valid progress file found. Starting fresh.\n")
            clear_progress()
    else:
        print("Starting a new job. Any previous progress will be cleared.\n")
        clear_progress()

    output_headers = ['DOI', 'Title', 'Authors', 'Journal', 'ISSN', 'Volume', 'Issue', 'Pages']
    
    if start_index == 0:
        required_header_len = output_start_index + len(output_headers)
        if len(header) < required_header_len:
            header.extend([''] * (required_header_len - len(header)))
        for i, h in enumerate(output_headers):
            header[output_start_index + i] = h

    dois_to_process = dois[start_index:]
    session_start_time = time.time()
    session_processed_count = 0
    
    with open(MALFORMED_LOG_FILENAME, 'a', encoding='utf-8') as malformed_log_file:
        if start_index == 0:
            malformed_log_file.write(f"\n--- Log started at {datetime.now().isoformat()} ---\n")

        for i in range(0, len(dois_to_process), args.batch_size):
            batch_start_time = time.time()
            batch_slice = dois_to_process[i:i + args.batch_size]
            
            batch_dois_to_query = [doi for doi in batch_slice if doi]
            
            metadata_items = []
            if batch_dois_to_query:
                metadata_items = get_metadata_in_batch(batch_dois_to_query, malformed_log_file)
            
            metadata_map = {item.get('DOI', '').lower(): item for item in metadata_items if item}
            
            for j, doi_or_none in enumerate(batch_slice):
                current_absolute_index = start_index + i + j
                target_row = data_rows[current_absolute_index]
                
                output_values = [''] * len(output_headers)
                if doi_or_none is not None:
                    item = metadata_map.get(doi_or_none.lower())
                    if item:
                        parsed_data = parse_metadata(item)
                        if not parsed_data.get('DOI'):
                             parsed_data['DOI'] = doi_or_none
                        output_values = [str(parsed_data.get(header, '')) for header in output_headers]

                required_row_len = output_start_index + len(output_headers)
                if len(target_row) < required_row_len:
                    target_row.extend([''] * (required_row_len - len(target_row)))

                for k, value in enumerate(output_values):
                    target_row[output_start_index + k] = value

            batch_end_time = time.time()
            batch_duration = batch_end_time - batch_start_time
            session_processed_count += len(batch_slice)
            total_processed_count = start_index + session_processed_count
            
            session_elapsed_time = time.time() - session_start_time
            eta_formatted = "Calculating..."
            if session_elapsed_time > 1:
                avg_speed = session_processed_count / session_elapsed_time
                dois_remaining = total_dois - total_processed_count
                if avg_speed > 0:
                    eta_seconds = dois_remaining / avg_speed
                    eta_formatted = format_time(eta_seconds)

            progress_str = (
                f"Batch {i // args.batch_size + 1}/{total_batches} took {batch_duration:.2f}s. "
                f"Processed {total_processed_count}/{total_dois} rows. "
                f"ETA: {eta_formatted}"
            )
            sys.stdout.write('\r' + progress_str.ljust(90))
            sys.stdout.flush()
            
            write_csv_safely(args.input_file, header, data_rows)
            save_progress(args.input_file, total_processed_count)
            
            time.sleep(args.wait_time)

    print("\n\nMetadata resolution complete. The file has been updated progressively.")
    clear_progress()

if __name__ == "__main__":
    main()
