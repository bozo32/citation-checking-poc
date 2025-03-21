#!/usr/bin/env python3
import os
import glob
import argparse
import json
import csv
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def parse_tei_file(tei_file_path):
    """
    Parse a TEI file to extract:
      - In-text citations: mapping citation_id -> list of <s> element strings that contain a <ref> with type "bibr"
      - Bibliography entries: mapping bib id (from xml:id attribute in <biblStruct>) -> raw reference note text
    """
    try:
        with open(tei_file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logging.error(f"Error reading {tei_file_path}: {e}")
        return None, None

    soup = BeautifulSoup(content, "xml")
    
    # Extract in-text citations from <s> elements
    in_text_citations = {}  # citation id -> list of sentence strings
    for s_tag in soup.find_all("s"):
        refs = s_tag.find_all("ref", {"type": "bibr"})
        if refs:
            # Get the full <s> element as a string (including child markup)
            sentence_str = str(s_tag)
            for ref in refs:
                target = ref.get("target", "").strip()
                if target.startswith("#"):
                    citation_id = target[1:]
                else:
                    citation_id = target
                if citation_id:
                    in_text_citations.setdefault(citation_id, []).append(sentence_str)
    
    # Extract bibliography entries from <biblStruct> elements
    bib_entries = {}  # bib id -> raw reference note text
    for bibl in soup.find_all("biblStruct"):
        bib_id = bibl.get("xml:id")
        if not bib_id:
            continue
        note = bibl.find("note", {"type": "raw_reference"})
        if note and note.get_text(strip=True):
            raw_ref = note.get_text(strip=True)
            bib_entries[bib_id] = raw_ref

    return in_text_citations, bib_entries

def process_tei_file(tei_file_path, output_dir):
    """
    Process one TEI file:
      - Extract in-text citations and bibliography entries.
      - Determine unmatched in-text citations and unmatched bibliography entries.
      - Compute overall 'clear' flag (True if both unmatched sets are empty).
      - Save a JSON file with the results.
    Returns the result object.
    """
    tei_filename = os.path.basename(tei_file_path)
    in_text_citations, bib_entries = parse_tei_file(tei_file_path)
    if in_text_citations is None or bib_entries is None:
        logging.error(f"Failed to parse {tei_file_path}.")
        return None

    # Determine unmatched citation IDs (present in text but not in bibliography)
    unmatched_citing = {cid: sentences for cid, sentences in in_text_citations.items() if cid not in bib_entries}

    # Determine unmatched bibliography entries (present in bibliography but not cited)
    unmatched_bibl = {bid: raw_ref for bid, raw_ref in bib_entries.items() if bid not in in_text_citations}

    clear_flag = (len(unmatched_citing) == 0 and len(unmatched_bibl) == 0)

    result = {
        "filename": tei_filename,
        "clear": clear_flag,
        "citing_sentences_without_corresponding_bibliography_entries": unmatched_citing,
        "bibliography_items_without_corresponding_in_text_citations": unmatched_bibl
    }

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)
    # Save JSON file with naming convention: filename-cit-bib.json
    json_filename = os.path.splitext(tei_filename)[0] + "-cit-bib.json"
    json_filepath = os.path.join(output_dir, json_filename)
    try:
        with open(json_filepath, "w", encoding="utf-8") as jf:
            json.dump(result, jf, indent=4)
        logging.info(f"Processed {tei_filename}: JSON saved as {json_filename}")
    except Exception as e:
        logging.error(f"Error writing JSON file for {tei_filename}: {e}")

    return result

def main():
    parser = argparse.ArgumentParser(
        description="Test in-text citations against bibliography entries in TEI files."
    )
    parser.add_argument(
        "-f", "--folder", required=True,
        help="Project home folder (TEI files are expected in the /tei subfolder)"
    )
    args = parser.parse_args()

    project_home = args.folder
    tei_folder = os.path.join(project_home, "tei")
    if not os.path.isdir(tei_folder):
        logging.error(f"TEI folder not found: {tei_folder}")
        return

    # Create output folder for JSON files: match-cit-bib inside project home
    output_folder = os.path.join(project_home, "match-cit-bib")
    os.makedirs(output_folder, exist_ok=True)

    # Process each TEI file
    tei_files = glob.glob(os.path.join(tei_folder, "*.tei.xml"))
    if not tei_files:
        logging.info("No TEI files found in the TEI folder.")
        return

    results = []
    for tei_file in tei_files:
        result = process_tei_file(tei_file, output_folder)
        if result:
            results.append(result)

    # Create CSV file match-cit-bib.csv in project home with columns "filename" and "clearstatus"
    csv_filepath = os.path.join(project_home, "match-cit-bib.csv")
    try:
        with open(csv_filepath, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=["filename", "clearstatus"])
            writer.writeheader()
            for res in results:
                filename = res["filename"]
                # If the filename ends with ".tei.xml", remove that extension
                if filename.endswith(".tei.xml"):
                    base_filename = filename[:-8]
                else:
                    base_filename, _ = os.path.splitext(filename)
                writer.writerow({"filename": base_filename, "clearstatus": res["clear"]})
        logging.info(f"CSV summary saved as {csv_filepath}")
    except Exception as e:
        logging.error(f"Error writing CSV file: {e}")

if __name__ == "__main__":
    main()

"""
Match-Cit-To-Bib Script Documentation
------------------------------------

Overview:
---------
The script "match-cit-to-bib.py" processes TEI XML files within a specified project folder to test in-text citations against bibliography entries. For each TEI XML file found in the "tei" subfolder of the project folder, the script extracts in-text citations (from <s> elements containing <ref type="bibr">) and bibliography entries (from <biblStruct> elements). It then compares these to determine unmatched in-text citations and unmatched bibliography entries, and computes a "clear" flag. The results are saved as a JSON file in an output subfolder named "match-cit-bib", and a CSV summary is generated in the project folder.

Requirements:
-------------
- Python 3.x installed on your system.
- The following Python modules must be available: os, glob, argparse, json, csv, logging, and BeautifulSoup (from bs4).
- A project folder containing a "tei" subfolder with TEI XML files.

Usage:
------
Run the script from the command line using the following syntax:

    python match-cit-bib.py -f <project_home_folder>

Example:
    python match-cit-bib.py -f /path/to/project_folder

Default Parameters:
-------------------
The script assumes:
- TEI XML files contain in-text citations marked with <ref type="bibr"> within <s> elements.
- Bibliography entries are defined in <biblStruct> elements with an "xml:id" attribute.
- Each bibliography entry includes a <note type="raw_reference"> containing the raw reference text.

Output:
-------
- The script creates an output subfolder named "match-cit-bib" within the project folder (if it does not already exist).
- For each TEI XML file processed, a JSON file is generated with the same base name as the TEI file and a "-cit-bib.json" extension.
- A CSV file named "match-cit-bib.csv" is also generated in the project folder, summarizing the matching status (clear flag) for each processed file.

Logging and Error Handling:
---------------------------
- Logging is configured to display messages at the INFO level to provide feedback during processing.
- If the provided project folder does not exist or contains no TEI XML files in the "tei" subfolder, the script logs an appropriate message.
- Any errors encountered during the processing of a TEI file (e.g., file read errors, JSON write errors) are logged as errors.

Customization:
--------------
If necessary, you can modify the parsing and processing logic in the functions "parse_tei_file" and "process_tei_file" to suit your specific TEI XML schema requirements.

Contact / Support:
------------------
For further assistance or to report issues, please refer to the inline comments within the script or contact the developer.

------------------------------------
End of Documentation
------------------------------------
"""