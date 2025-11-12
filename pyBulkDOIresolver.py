import os
import argparse
import requests
import json
import time
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
CROSSREF_EMAIL = os.getenv("CROSSREF_EMAIL", "anonymous@example.com")
CROSSREF_API_URL = "https://api.crossref.org/works"
PROGRESS_FILE = ".inProgress"

# --- Main Script Logic ---
def get_metadata_in_batch(dois):
    """
    Sends a bulk GET request to the Crossref API with a retry/backoff mechanism.
    """
    headers = {
        'User-Agent': f'DOIResolver/1.0 (mailto:{CROSSREF_EMAIL})'
    }
    filter_string = ','.join([f"doi:{doi}" for doi in dois])
    params = {'filter': filter_string}

    # Retry loop for handling API rate limits
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(CROSSREF_API_URL, headers=headers, params=params)
            
            # Check for specific backoff status codes
            if response.status_code in [429, 503]:
                print(f"  - Received status {response.status_code}. Backing off for 10 seconds...")
                time.sleep(10)
                # Continue to the next attempt in the loop
                continue

            response.raise_for_status()  # Raise an exception for other HTTP errors (like 404, 500)
            
            results = response.json()
            if results and 'message' in results and 'items' in results['message']:
                return results['message']['items']
            else:
                return [] # Success, but no items found

        except requests.exceptions.HTTPError as e:
            print(f"  - Unrecoverable HTTP Error for this batch: {e}")
            return [] # Hard failure for this batch
        except requests.exceptions.RequestException as e:
            print(f"  - A network error occurred: {e}")
            if attempt < max_retries - 1:
                print("  - Retrying after a short delay...")
                time.sleep(2)
            continue # Retry on network errors

    print(f"  - Batch failed after {max_retries} attempts. Skipping this batch.")
    return []


def save_progress(filename, index):
    """Saves the current progress to the .inProgress file."""
    with open(PROGRESS_FILE, 'w') as f:
        f.write(f"{filename}\n{index}")

def load_progress():
    """Loads progress from the .inProgress file. Returns (filename, index)."""
    if not os.path.exists(PROGRESS_FILE):
        return None, 0
    try:
        with open(PROGRESS_FILE, 'r') as f:
            filename = f.readline().strip()
            index = int(f.readline().strip())
            return filename, index
    except (ValueError, IndexError):
        # Handle corrupted or empty progress file
        return None, 0

def clear_progress():
    """Removes the .inProgress file on successful completion or fresh start."""
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

def parse_metadata(item):
    """Parses the JSON response for a single DOI and extracts relevant fields."""
    doi = item.get('DOI', '')
    title = ''.join(item.get('title', ['']))
    
    authors = []
    if 'author' in item and isinstance(item['author'], list):
        for author in item['author']:
            if isinstance(author, dict):
                given = author.get('given', '')
                family = author.get('family', '')
                author_name = f"{given} {family}".strip()
                if author_name:
                    authors.append(author_name)
    
    journal = ''.join(item.get('container-title', ['']))
    
    issn = ""
    if 'ISSN' in item and isinstance(item['ISSN'], list):
        issn = ', '.join(item['ISSN'])
        
    volume = item.get('volume', '')
    issue = item.get('issue', '')
    pages = item.get('page', '')

    return {
        'DOI': doi,
        'Title': title,
        'Authors': '; '.join(authors),
        'Journal': journal,
        'ISSN': issn,
        'Volume': volume,
        'Issue': issue,
        'Pages': pages
    }

def main():
    parser = argparse.ArgumentParser(description="Bulk resolve DOI URLs with resume and backoff functionality.")
    parser.add_argument("filename", help="The input file containing DOI URLs (one per line).")
    parser.add_argument("batch_size", type=int, nargs='?', default=45, help="DOIs per batch request (default: 45).")
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted job.")
    args = parser.parse_args()

    # --- Resume Logic ---
    start_index = 0
    output_mode = 'w' # Overwrite by default
    
    if args.resume:
        saved_filename, saved_index = load_progress()
        if saved_filename == args.filename:
            start_index = saved_index
            output_mode = 'a' # Append if resuming
            print(f"Resuming job for '{args.filename}' from DOI number {start_index + 1}.")
        else:
            print("Warning: --resume flag used, but no valid progress file found for this filename. Starting fresh.")
            clear_progress()
    else:
        print("Starting a new job. Any previous progress will be cleared.")
        clear_progress()
    
    # --- File Reading ---
    try:
        with open(args.filename, 'r') as f:
            dois = [
                line.strip().replace('https://doi.org/', '').replace('http://doi.org/', '').replace('doi.org/', '')
                for line in f if line.strip()
            ]
    except FileNotFoundError:
        print(f"Error: The file '{args.filename}' was not found.")
        return

    if not dois:
        print("No DOIs found in the input file.")
        return

    output_filename = "resolved_metadata.tsv"
    headers = ['DOI', 'Title', 'Authors', 'Journal', 'ISSN', 'Volume', 'Issue', 'Pages']

    # --- Main Processing Loop ---
    with open(output_filename, output_mode, encoding='utf-8') as out_file:
        # Write headers only if it's a new file
        if start_index == 0:
            out_file.write('\t'.join(headers) + '\n')

        # Slice the list to start from the correct index
        dois_to_process = dois[start_index:]
        
        for i in range(0, len(dois_to_process), args.batch_size):
            batch_dois = dois_to_process[i:i + args.batch_size]
            current_absolute_index = start_index + i
            
            print(f"Processing batch of {len(batch_dois)} DOIs (starting from #{current_absolute_index + 1})...")
            
            metadata_items = get_metadata_in_batch(batch_dois)
            
            metadata_map = {item.get('DOI', '').lower(): item for item in metadata_items}

            for doi in batch_dois:
                item = metadata_map.get(doi.lower())
                if item:
                    parsed_data = parse_metadata(item)
                    row = [str(parsed_data.get(header, '')) for header in headers]
                    out_file.write('\t'.join(row) + '\n')
                else:
                    out_file.write(f"{doi}\t" + '\t'.join(['' for _ in headers[1:]]) + '\n')
            
            # Save progress after each successful batch
            save_progress(args.filename, current_absolute_index + len(batch_dois))

    # --- Cleanup ---
    print(f"\nMetadata resolution complete. Results saved to '{output_filename}'.")
    clear_progress() # Clean up progress file on success

if __name__ == "__main__":
    main()