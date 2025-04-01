import os
import json
import re
import time
import random
import requests
import argparse
from scholarly import scholarly

# Define the base directory where files will be stored
BASE_DIR = "/home/tamas002/aistuff/citation-checker-poc/forward_citation_searches/metadata"
os.makedirs(BASE_DIR, exist_ok=True)

# Overall citation graph: mapping from "Author: DOI" to a dict of citing records from OpenAlex and scholarly extras.
# For OpenAlex records, each item is a dict with keys "doi" and "pdf_url" (which may be None if no link is available).
citation_graph = {}

# Helper function to sanitize strings for file names
def sanitize_filename(text):
    return re.sub(r'[^\w\-]', '_', text)

# Parse a line from the source file.
# Expected format: "Author, doi.org/10.xxxx" or "Author, doi:10.xxxx"
def parse_line(line):
    parts = line.strip().split(',')
    if len(parts) < 2:
        return None, None
    author = parts[0].strip()
    doi_str = parts[1].strip()
    doi_str = doi_str.replace("doi.org/", "").replace("doi:", "").strip()
    return author, doi_str

# Query OpenAlex for a work using its DOI
def get_openalex_work(doi):
    url = f"https://api.openalex.org/works/doi:{doi}"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()
    else:
        print(f"OpenAlex query failed for DOI {doi} with status code {r.status_code}")
        return None

# Retrieve citing works metadata from OpenAlex given an OpenAlex work ID
def get_openalex_citing_metadata(openalex_id):
    citing_metadata = []
    base_url = "https://api.openalex.org/works"
    params = {
        "filter": f"cites:{openalex_id}",
        "per_page": 200  # maximum per page
    }
    while True:
        r = requests.get(base_url, params=params)
        if r.status_code != 200:
            print("Error querying OpenAlex for citing works.")
            break
        data = r.json()
        citing_metadata.extend(data.get("results", []))
        meta = data.get("meta", {})
        next_cursor = meta.get("next_cursor")
        if not next_cursor:
            break
        params["cursor"] = next_cursor
        time.sleep(random.uniform(1, 3))
    return citing_metadata

# Retrieve citing DOIs from scholarly (Google Scholar) for the given publication.
# Returns a dictionary mapping a DOI (or fallback pub_url) to the filled publication record.
def get_scholarly_citing_records(pub):
    scholarly_records = {}
    try:
        citing_gen = scholarly.citedby(pub)
        for citing_pub in citing_gen:
            citing_pub = scholarly.fill(citing_pub)
            doi_val = None
            if "bib" in citing_pub and "doi" in citing_pub["bib"]:
                doi_val = citing_pub["bib"]["doi"]
            if not doi_val:
                doi_val = citing_pub.get("pub_url", "no_doi")
            scholarly_records[doi_val.lower()] = citing_pub
            time.sleep(random.uniform(3, 7))
    except Exception as e:
        print(f"Error querying scholarly for citing works: {e}")
    return scholarly_records

# Retrieve BibTeX entry from scholarly for a given DOI
def get_bibtex_from_doi(doi):
    try:
        search_query = scholarly.search_pubs(doi)
        pub = next(search_query)
        pub = scholarly.fill(pub)
        bibtex = scholarly.bibtex(pub)
        return bibtex
    except Exception as e:
        print(f"Error retrieving BibTeX for DOI {doi}: {e}")
        return None

# Process a single DOI with its author
def process_doi(doi, author):
    doi = doi.strip()
    if not doi:
        return
    key = f"{author}: {doi}"
    print(f"\nProcessing {key}")
    citation_graph[key] = {"openalex": [], "scholarly_extra": []}
    
    # Build a sanitized filename from the author and DOI
    sanitized = sanitize_filename(f"{author}_{doi}")

    # --- Query OpenAlex ---
    openalex_work = get_openalex_work(doi)
    if openalex_work:
        openalex_id = openalex_work.get("id")
        openalex_citing_metadata = get_openalex_citing_metadata(openalex_id)
        openalex_citing_dois = set()
        for record in openalex_citing_metadata:
            doi_raw = record.get("doi")
            if doi_raw:
                doi_citing = doi_raw.lower()
                # Look for a download link (pdf_url) in best_oa_location first, then primary_location.
                pdf_url = None
                best = record.get("best_oa_location")
                if best and best.get("pdf_url"):
                    pdf_url = best.get("pdf_url")
                else:
                    primary = record.get("primary_location")
                    if primary and primary.get("pdf_url"):
                        pdf_url = primary.get("pdf_url")
                openalex_citing_dois.add(doi_citing)
                citation_graph[key]["openalex"].append({"doi": doi_citing, "pdf_url": pdf_url})
        # Save OpenAlex metadata to a JSON file
        json_file_path = os.path.join(BASE_DIR, f"{sanitized}_openalex_citing.json")
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(openalex_citing_metadata, f, indent=2)
        print(f"OpenAlex returned {len(openalex_citing_dois)} citing DOIs for {key}")
    else:
        openalex_citing_dois = set()

    # --- Query scholarly for citing records ---
    try:
        search_query = scholarly.search_pubs(doi)
        pub = next(search_query)
        pub = scholarly.fill(pub)
    except Exception as e:
        print(f"Error retrieving original publication from scholarly for {key}: {e}")
        return

    scholarly_records = get_scholarly_citing_records(pub)
    scholarly_citing_dois = set(scholarly_records.keys())
    print(f"Scholarly returned {len(scholarly_citing_dois)} citing records for {key}")

    # --- Compute the delta: records from scholarly not present in OpenAlex ---
    additional_dois = scholarly_citing_dois - openalex_citing_dois
    print(f"Found {len(additional_dois)} additional citing records from scholarly for {key}")

    # Save additional scholarly records' BibTeX information in a file
    bibfile_path = os.path.join(BASE_DIR, f"{sanitized}_scholarly_extra.bib")
    with open(bibfile_path, 'w', encoding='utf-8') as bibfile:
        for extra_doi in additional_dois:
            if extra_doi == "no_doi":
                continue
            bibtex = get_bibtex_from_doi(extra_doi)
            if bibtex:
                bibfile.write(bibtex + "\n\n")
                citation_graph[key]["scholarly_extra"].append(extra_doi)
            time.sleep(random.uniform(3, 7))

    # Pause between processing different DOIs
    time.sleep(random.uniform(10, 20))

def main():
    parser = argparse.ArgumentParser(description="Forward citation search script")
    parser.add_argument("-f", "--file", required=True, help="Path to a text file with one record per row (format: Author, DOI)")
    args = parser.parse_args()

    doi_file = args.file
    if not os.path.isfile(doi_file):
        print(f"File not found: {doi_file}")
        return

    # Read and parse the source file: each line should be "Author, DOI"
    with open(doi_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in lines:
        author, doi = parse_line(line)
        if author and doi:
            process_doi(doi, author)
        else:
            print(f"Skipping invalid line: {line.strip()}")

    # Save the overall citation graph mapping as a JSON file
    citation_graph_path = os.path.join(BASE_DIR, "citation_graph.json")
    with open(citation_graph_path, 'w', encoding='utf-8') as json_file:
        json.dump(citation_graph, json_file, indent=2)

    print("\nFinished processing all DOIs.")

if __name__ == "__main__":
    main()
