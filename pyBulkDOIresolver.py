import os
import argparse
import requests
import json
import time
import sys
import math
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
CROSSREF_EMAIL = os.getenv("CROSSREF_EMAIL", "anonymous@example.com")
CROSSREF_API_URL = "https://api.crossref.org/works"
PROGRESS_FILE = ".inProgress"
DEFAULT_BATCH_SIZE = 45 # <<< Easy to edit default batch size is here

# --- Helper Functions ---

def format_time(seconds):
    """Formats seconds into a human-readable HH:MM:SS string."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

# --- Main Script Logic ---

def get_metadata_in_batch(dois):
    """Sends a bulk GET request with a retry/backoff mechanism."""
    headers = {'User-Agent': f'DOIResolver/1.0 (mailto:{CROSSREF_EMAIL})'}
    filter_string = ','.join([f"doi:{doi}" for doi in dois])
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
    parser = argparse.ArgumentParser(description="Bulk resolve DOI URLs with resume and backoff functionality.")
    parser.add_argument("filename", help="The input file containing DOI URLs (one per line).")
    # --- The default value is now set using the constant from the top ---
    parser.add_argument("batch_size", type=int, nargs='?', default=DEFAULT_BATCH_SIZE, 
                        help=f"DOIs per batch request (default: {DEFAULT_BATCH_SIZE}).")
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted job.")
    args = parser.parse_args()

    try:
        with open(args.filename, 'r') as f:
            dois = [line.strip().replace('https://doi.org/', '').replace('http://doi.org/', '').replace('doi.org/', '')
                    for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: The file '{args.filename}' was not found.", file=sys.stderr)
        return

    if not dois:
        print("No DOIs found in the input file.")
        return

    total_dois = len(dois)
    total_batches = math.ceil(total_dois / args.batch_size)
    print("-" * 50)
    print("Job Summary:")
    print(f"  - Input file:       {args.filename}")
    print(f"  - Total DOIs found: {total_dois}")
    print(f"  - Batch size:         {args.batch_size}")
    print(f"  - Total batches:      {total_batches}")
    print("-" * 50)

    start_index, output_mode = 0, 'w'
    if args.resume:
        saved_filename, saved_index = load_progress()
        if saved_filename == args.filename and saved_index > 0:
            start_index, output_mode = saved_index, 'a'
            print(f"Resuming job from DOI number {start_index + 1}.\n")
        else:
            print("Warning: --resume specified, but no valid progress file found. Starting fresh.\n")
            clear_progress()
    else:
        print("Starting a new job. Any previous progress will be cleared.\n")
        clear_progress()

    output_filename = "resolved_metadata.tsv"
    headers = ['DOI', 'Title', 'Authors', 'Journal', 'ISSN', 'Volume', 'Issue', 'Pages']
    
    dois_to_process = dois[start_index:]
    session_start_time = time.time()
    session_processed_count = 0

    with open(output_filename, output_mode, encoding='utf-8') as out_file:
        if start_index == 0: out_file.write('\t'.join(headers) + '\n')
        
        for i in range(0, len(dois_to_process), args.batch_size):
            batch_start_time = time.time()
            batch_dois = dois_to_process[i:i + args.batch_size]
            current_absolute_index = start_index + i
            
            metadata_items = get_metadata_in_batch(batch_dois)
            metadata_map = {item.get('DOI', '').lower(): item for item in metadata_items if item}

            for doi in batch_dois:
                item = metadata_map.get(doi.lower())
                parsed_data = parse_metadata(item) if item else {}
                row = [str(parsed_data.get(header, '')) for header in headers]
                if not row[0]: row[0] = doi
                out_file.write('\t'.join(row) + '\n')
            
            batch_end_time = time.time()
            batch_duration = batch_end_time - batch_start_time
            session_processed_count += len(batch_dois)
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
                f"Batch {i//args.batch_size + 1}/{total_batches} took {batch_duration:.2f}s. "
                f"Processed {total_processed_count}/{total_dois} DOIs. "
                f"ETA: {eta_formatted}"
            )
            sys.stdout.write('\r' + progress_str.ljust(85))
            sys.stdout.flush()
            
            save_progress(args.filename, current_absolute_index + len(batch_dois))
            time.sleep(0.34)

    print("\n\nMetadata resolution complete.")
    clear_progress()

if __name__ == "__main__":
    main()
