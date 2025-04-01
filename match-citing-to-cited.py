#!/usr/bin/env python3
import os
import glob
import json
import csv
import argparse
import logging
import re
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def get_base_name(filename):
    """Return the base name of a file (without the '.tei.xml' extension)."""
    base = os.path.basename(filename)
    base = re.sub(r'\.tei\.xml$', '', base, flags=re.IGNORECASE)
    return base

def load_crossref_json(json_path):
    """
    Load the JSON file from the consolidation folder.
    The JSON is expected to be either a list of records or a dict with a "records" key.
    Each record should contain 'bib_item' and 'dl_filename' fields.
    Returns a mapping from bib_item to dl_filename (or "missing" if empty).
    """
    try:
        with open(json_path, "r", encoding="utf-8") as jf:
            data = json.load(jf)
            if isinstance(data, list):
                records = data
            else:
                records = data.get("records", [])
            mapping = {}
            for rec in records:
                bib_item = rec.get("bib_item", "").strip()
                dl_filename = rec.get("dl_filename", "").strip()
                if bib_item:
                    mapping[bib_item] = dl_filename if dl_filename else "missing"
            return mapping
    except Exception as e:
        logging.error(f"Error loading JSON file {json_path}: {e}")
        return {}

def extract_citing_sentences(tei_path):
    """
    Extract all <s> elements from the citing TEI file.
    Returns a list of BeautifulSoup tags.
    """
    try:
        with open(tei_path, "r", encoding="utf-8") as f:
            content = f.read()
        soup = BeautifulSoup(content, "xml")
        sentences = soup.find_all("s")
        return sentences
    except Exception as e:
        logging.error(f"Error processing TEI file {tei_path}: {e}")
        return []

def extract_citations_from_sentence(s):
    """
    Given a BeautifulSoup <s> element, return a list of bib_ids 
    extracted from all <ref> tags that have a "target" attribute.
    The leading '#' (if present) is removed.
    """
    refs = s.find_all("ref", target=True)
    bib_ids = []
    for ref in refs:
        target = ref.get("target", "")
        if target.startswith("#"):
            bib_ids.append(target[1:])
        elif target:
            bib_ids.append(target)
    return bib_ids

def write_csv(output_folder, base_name, rows):
    """
    Write the matching information into a CSV file named "{base_name}-matching.csv"
    in the specified output folder.
    """
    os.makedirs(output_folder, exist_ok=True)
    csv_filename = f"{base_name}-matching.csv"
    csv_path = os.path.join(output_folder, csv_filename)
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["bib_id", "citing_sentence", "cited_record"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    logging.info(f"Matching CSV saved to {csv_path}")

def process_citing_file(tei_file, consolidation_folder, home_folder):
    """
    For a given citing TEI file, locate its corresponding JSON file in the
    consolidation folder, extract all citation references from its <s> elements,
    and write out a CSV mapping each bib_id to the downloaded file name.
    """
    base_name = get_base_name(tei_file)
    json_pattern = os.path.join(consolidation_folder, f"{base_name}.tei-crossref.json")
    json_files = glob.glob(json_pattern)
    if not json_files:
        logging.warning(f"No JSON file found for {tei_file} (expected: {json_pattern}). Skipping.")
        return
    json_path = json_files[0]
    dl_mapping = load_crossref_json(json_path)
    sentences = extract_citing_sentences(tei_file)
    rows = []
    for s in sentences:
        # Use the raw string representation (with XML tags) as the citing sentence.
        citing_sentence_raw = str(s)
        bib_ids = extract_citations_from_sentence(s)
        if bib_ids:
            for bib_id in bib_ids:
                cited_record = dl_mapping.get(bib_id, "missing")
                rows.append({
                    "bib_id": bib_id,
                    "citing_sentence": citing_sentence_raw,
                    "cited_record": cited_record
                })
    if rows:
        # Create output folder named after the base name of the TEI file in the home folder.
        output_folder = os.path.join(home_folder, base_name)
        write_csv(output_folder, base_name, rows)
    else:
        logging.info(f"No citing sentences with citation references found in {tei_file}.")

def main():
    parser = argparse.ArgumentParser(description="Match citing sentences to downloaded cited records.")
    parser.add_argument("-f", "--folder", required=True,
                        help="Home folder containing subfolders 'tei' and 'consolidation'.")
    args = parser.parse_args()
    home_folder = os.path.abspath(args.folder)
    tei_folder = os.path.join(home_folder, "tei")
    consolidation_folder = os.path.join(home_folder, "consolidation")
    if not os.path.isdir(tei_folder):
        logging.error(f"TEI folder not found at {tei_folder}")
        return
    if not os.path.isdir(consolidation_folder):
        logging.error(f"Consolidation folder not found at {consolidation_folder}")
        return
    tei_files = glob.glob(os.path.join(tei_folder, "*.tei.xml"))
    if not tei_files:
        logging.info(f"No TEI files found in {tei_folder}")
        return
    for tei_file in tei_files:
        logging.info(f"Processing citing TEI file: {tei_file}")
        process_citing_file(tei_file, consolidation_folder, home_folder)

if __name__ == "__main__":
    main()

"""
Matching Script Documentation
------------------------------

Overview:
---------
The script “matching.py” processes citing TEI files and corresponding JSON files found in the “tei” and “consolidation” subfolders under the project home directory. For each citing TEI file:
    • It extracts all citing sentences (each enclosed in an <s> element).
    • It identifies citation references within each sentence by extracting the bib item identifier from the "target" attribute of <ref> tags (removing any leading '#' characters).
    • It loads the corresponding JSON file from the consolidation folder (the JSON file is expected to have the same base name as the TEI file, with the extension “.tei-crossref.json”). This JSON contains an array of bib item records (or a dictionary with a “records” key), each record including “bib_item” and “dl_filename” fields.
    • For every citation reference found in the TEI file, the script maps the bib item identifier to the corresponding downloaded cited record filename (or “missing” if not available).
    • The script then writes a CSV file named “<citing_article>-matching.csv” (where <citing_article> is derived from the citing TEI filename) in a folder also named after the citing article under the project home directory.
    • The CSV file contains the following columns:
          - bib_id: the bibliography item identifier (from the TEI citation reference).
          - citing_sentence: the full raw content (including XML tags) of the citing sentence containing the reference.
          - cited_record: the downloaded cited record’s base filename (or “missing” if no file was retrieved).

Requirements:
-------------
- Python 3.x installed on your system.
- The following Python modules must be available: os, glob, json, csv, argparse, logging, re, and bs4 (BeautifulSoup).
- The project home directory must contain a “tei” folder with citing TEI files and a “consolidation” folder containing JSON files produced by the consolidation process.
- The JSON files are expected to be either a list of records or a dictionary with a “records” key. Each record must include “bib_item” and “dl_filename” fields.

Usage:
------
Run the script from the command line using the following syntax:

    python matching.py -f <project_home_directory>

Example:

    python matching.py -f /path/to/project_home

Default Parameters:
-------------------
- The script expects citing TEI files to be located in the “tei” subfolder under the project home directory.
- The corresponding JSON files should be located in the “consolidation” subfolder under the project home directory and follow the naming pattern “<base_name>.tei-crossref.json”, where <base_name> is derived from the citing TEI filename.
- The resulting CSV file is saved in a folder named after the citing article (derived from the TEI filename) within the project home directory.
- Each CSV file is named “<citing_article>-matching.csv” and contains three columns:
      • bib_id – the bibliography item identifier extracted from the TEI citation reference.
      • citing_sentence – the raw (unsanitized) full text of the citing sentence.
      • cited_record – the downloaded cited record’s filename (or “missing” if not available).

Output:
-------
- For each citing TEI file processed, a folder is created under the project home directory (named after the TEI file’s base name).
- Within this folder, a CSV file named “<citing_article>-matching.csv” is generated.
- The CSV maps each citation reference (bib item) from the TEI file to the corresponding downloaded cited record filename (from the JSON file) or “missing” if no file was retrieved.

Logging and Error Handling:
---------------------------
- Logging is configured at the INFO level to report progress and errors.
- If the required subfolders (“tei” or “consolidation”) are missing, or if no TEI files are found, the script logs an error and aborts.
- Any errors during JSON loading, TEI processing, or CSV writing are logged.

Customization:
--------------
- You may modify the regular expressions used in the get_base_name function if your file naming conventions differ.
- The CSV file naming convention and output folder structure can be adjusted by modifying the write_csv function.
- If your TEI files use a different structure for citing sentences or references, you can adjust the extract_citing_sentences and extract_citations_from_sentence functions accordingly.

Contact / Support:
------------------
For further assistance or to report issues, please refer to the inline comments within the script or contact the developer.

------------------------------
End of Documentation
------------------------------
"""