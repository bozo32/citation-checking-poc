#!/usr/bin/env python3
import os
import glob
import json
import logging
import argparse
import requests
import re
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def sanitize_filename(filename):
    """Replace invalid filename characters with underscores."""
    return "".join(c if c.isalnum() or c in (' ', '.', '_') else '_' for c in filename).replace(' ', '_')

def download_pdf(url):
    """
    Download a PDF from the provided URL.
    Returns the PDF content if successful, otherwise returns None.
    """
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200 and 'application/pdf' in response.headers.get("Content-Type", ""):
            return response.content
        else:
            logging.error(f"Failed to download PDF from {url}; status: {response.status_code} or wrong content type.")
    except Exception as e:
        logging.error(f"Exception downloading PDF from {url}: {e}")
    return None

def process_pdf_with_grobid(pdf_path, grobid_url, output_dir):
    """
    Send a PDF file to the Grobid API and return the TEI XML.
    The TEI XML is saved in output_dir with the same base filename (extension ".tei.xml").
    """
    try:
        with open(pdf_path, 'rb') as f:
            files = {'input': f}
            params = {
                'consolidateHeader': '1',
                'consolidateCitations': '1',
                'includeRawAffiliations': '1',
                'includeRawCitations': '1',
                'segmentSentences': '1'
            }
            response = requests.post(grobid_url, files=files, data=params)
            if response.status_code == 200:
                tei_xml = response.text
                os.makedirs(output_dir, exist_ok=True)
                base = os.path.splitext(os.path.basename(pdf_path))[0]
                tei_filename = f"{base}.tei.xml"
                tei_output_path = os.path.join(output_dir, tei_filename)
                with open(tei_output_path, "w", encoding="utf-8") as f_out:
                    f_out.write(tei_xml)
                logging.info(f"Grobid processing succeeded for {pdf_path}. TEI saved to {tei_output_path}")
                return tei_xml
            else:
                logging.error(f"Grobid failed for {pdf_path} with status {response.status_code}.")
    except Exception as e:
        logging.error(f"Exception processing {pdf_path} with Grobid: {e}")
    return None

def test_grobid_api(grobid_url):
    """
    Test the Grobid API by querying its health endpoint.
    Modifies the supplied URL to use the 'health' endpoint.
    Exits if the test fails.
    """
    if "processFulltextDocument" not in grobid_url:
        grobid_url = grobid_url.rstrip("/") + "/api/processFulltextDocument"
    health_url = grobid_url.replace("processFulltextDocument", "health")
    try:
        resp = requests.get(health_url, timeout=10)
        if resp.status_code == 200:
            logging.info("Grobid API health check succeeded.")
        else:
            logging.error(f"Grobid API health check failed with status {resp.status_code} at {health_url}")
            exit(1)
    except Exception as e:
        logging.error(f"Error testing Grobid API at {health_url}: {e}")
        exit(1)
    return grobid_url

def process_json_file(json_filepath, project_home, grobid_url):
    """
    Process a citing article JSON file from the consolidation folder.
    For each bib item record in the JSON file:
      - If the "retrievable" field starts with "http", download the PDF from that URL.
      - Rename the PDF using a sanitized version of the DOI from "crossref_doi" if available; otherwise use the bib_item.
      - Save the PDF in <project_home>/<citing_article>/PDF.
      - Process the PDF via Grobid and save the resulting TEI XML in <project_home>/<citing_article>/TEI.
      - Update the bib item record by adding a new key "dl_filename" (within that record) set to the base filename (without extension) if successful, or an empty string otherwise.
    The updated JSON file is written back with the same structure as it was originally.
    """
    try:
        with open(json_filepath, "r", encoding="utf-8") as jf:
            loaded = json.load(jf)
    except Exception as e:
        logging.error(f"Error loading JSON file {json_filepath}: {e}")
        return

    # Determine if the loaded JSON is a dictionary or a list.
    if isinstance(loaded, dict):
        records = loaded.get("records", [])
        original_structure = "dict"
    elif isinstance(loaded, list):
        records = loaded
        original_structure = "list"
    else:
        logging.error(f"Unexpected JSON structure in {json_filepath}")
        return

    # Derive the citing article name from the JSON filename.
    base_json = os.path.basename(json_filepath)
    citing_article = base_json.replace(".tei-crossref.json", "")
    article_folder = os.path.join(project_home, citing_article)
    pdf_folder = os.path.join(article_folder, "PDF")
    tei_folder = os.path.join(article_folder, "TEI")
    os.makedirs(pdf_folder, exist_ok=True)
    os.makedirs(tei_folder, exist_ok=True)

    for record in records:
        bib_item = record.get("bib_item", "").strip()
        retrievable = record.get("retrievable", "").strip()
        if retrievable.startswith("http"):
            doi = record.get("crossref_doi", "").strip()
            if doi:
                base_filename = sanitize_filename(doi)
            else:
                base_filename = sanitize_filename(bib_item)
            pdf_filename = f"{base_filename}.pdf"
            pdf_path = os.path.join(pdf_folder, pdf_filename)
            if not os.path.exists(pdf_path):
                logging.info(f"Downloading PDF for bib item '{bib_item}' from {retrievable}")
                pdf_content = download_pdf(retrievable)
                if pdf_content:
                    try:
                        with open(pdf_path, "wb") as pf:
                            pf.write(pdf_content)
                        logging.info(f"Saved PDF as {pdf_path}")
                    except Exception as e:
                        logging.error(f"Error saving PDF for bib item '{bib_item}': {e}")
                        record["dl_filename"] = ""
                        continue
                else:
                    logging.error(f"PDF download failed for bib item '{bib_item}'")
                    record["dl_filename"] = ""
                    continue
            else:
                logging.info(f"PDF already exists for bib item '{bib_item}'")
            tei_xml = process_pdf_with_grobid(pdf_path, grobid_url, tei_folder)
            if tei_xml:
                record["dl_filename"] = base_filename
            else:
                record["dl_filename"] = ""
        else:
            record["dl_filename"] = ""

    # Write updated JSON back using the original structure.
    try:
        if original_structure == "dict":
            loaded["records"] = records
            updated_data = loaded
        else:
            updated_data = records
        with open(json_filepath, "w", encoding="utf-8") as jf:
            json.dump(updated_data, jf, indent=4)
        logging.info(f"Updated JSON file saved: {json_filepath}")
    except Exception as e:
        logging.error(f"Error writing updated JSON file {json_filepath}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Retrieve PDFs for citing articles and process via Grobid.")
    parser.add_argument("-f", "--folder", required=True,
                        help="Full path to the project home directory.")
    parser.add_argument("-p", "--grobid", required=True,
                        help="Grobid API URL (e.g., http://127.0.0.1:8070 or http://127.0.0.1:8070/api/processFulltextDocument).")
    args = parser.parse_args()
    project_home = args.folder
    grobid_url = args.grobid
    if "processFulltextDocument" not in grobid_url:
        grobid_url = grobid_url.rstrip("/") + "/api/processFulltextDocument"
    grobid_url = test_grobid_api(grobid_url)

    json_folder = os.path.join(project_home, "consolidation")
    if not os.path.exists(json_folder):
        logging.error(f"Folder {json_folder} does not exist.")
        return
    json_files = glob.glob(os.path.join(json_folder, "*.json"))
    if not json_files:
        logging.info(f"No JSON files found in {json_folder}.")
        return
    for json_filepath in json_files:
        logging.info(f"Processing JSON file: {json_filepath}")
        process_json_file(json_filepath, project_home, grobid_url)

if __name__ == "__main__":
    main()

    """
    
⸻

Retrieve Script Documentation

⸻

Overview:
The script “retrieve.py” processes citing article JSON files found in the “consolidation” folder under the project home directory. Each JSON file contains an array of bib item records (or is wrapped in a dictionary with a “records” key). For each bib item record:
	•	If the “retrievable” field begins with “http”, the script downloads the corresponding PDF.
	•	The PDF is renamed using a sanitized version of the DOI from “crossref_doi” (if available) or the bib item identifier if not.
	•	The PDF is saved in a “PDF” subfolder inside a folder named after the citing article (derived from the JSON filename).
	•	The PDF is then processed via the Grobid API (with the URL provided via the -p flag), and the resulting TEI XML output is saved in a “TEI” subfolder.
	•	Each bib item record is updated by adding a new key “dl_filename” (inside the record) that holds the base filename (without extension) if both PDF retrieval and Grobid processing are successful; otherwise, it remains an empty string.
	•	The updated JSON file is saved using the same structure (list or dictionary) as the original.

Before processing, the script tests the Grobid API’s health (by querying its “health” endpoint) and exits if the API is not responding.

Requirements:
	•	Python 3.x installed.
	•	The following Python modules must be available: os, glob, json, logging, requests, argparse, re, and bs4 (BeautifulSoup).
	•	Access to a running Grobid API instance (the URL is provided via the -p flag).
	•	JSON files produced by the consolidation process must reside in the “consolidation” folder within the project home directory.
	•	A stable Internet connection is required for downloading PDFs and accessing the Grobid API.

Usage:
Run the script from the command line using:

    python retrieve.py -f <project_home_directory> -p <grobid_API_url>

Example:

    python retrieve.py -f /path/to/project_home -p http://127.0.0.1:8070

    Default Parameters:
	•	The script looks for JSON files in <project_home>/consolidation.
	•	For each bib item record:
	•	The “retrievable” field is used as the URL to download the PDF.
	•	The PDF is renamed using a sanitized version of “crossref_doi” (if available) or the bib_item value.
	•	The PDF is saved in <project_home>/<citing_article>/PDF.
	•	The PDF is processed by Grobid; the resulting TEI XML is saved in <project_home>/<citing_article>/TEI.
	•	The bib item record is updated with a new key “dl_filename” (inside the record) containing the base filename (without extension) if successful, or an empty string if not.
	•	The updated JSON file overwrites the original, preserving its structure (list or dictionary).

Output:
	•	For each citing article JSON file processed, a folder is created (named after the citing article, derived from the JSON filename) under the project home directory.
	•	Retrieved PDFs are stored in the “PDF” subfolder and the corresponding TEI XML files in the “TEI” subfolder.
	•	The original JSON file in the “consolidation” folder is updated with the “dl_filename” key in each bib item record.

Logging and Error Handling:
	•	Logging is configured at the INFO level to report progress and errors.
	•	If the project home directory, consolidation folder, or JSON files are missing, the script logs an error and aborts.
	•	Errors during PDF download, file saving, or Grobid processing are logged, and the corresponding bib item record’s “dl_filename” is set to an empty string.

Customization:
	•	You can modify the PDF download logic or the Grobid API parameters in the helper functions.
	•	The file naming convention (using sanitized DOIs or bib item identifiers) can be adjusted if needed.
	•	The script uses only the “retrievable” field from the JSON for PDF retrieval.

Contact / Support:
For further assistance or to report issues, please refer to the inline comments within the script or contact the developer.

    """