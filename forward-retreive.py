#!/usr/bin/env python3
import os
import json
import re
import time
import random
import argparse
import requests
import logging
import subprocess
import tempfile
import glob
import shutil

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def sanitize_filename(filename):
    """Replace invalid filename characters with underscores."""
    return re.sub(r'[^\w\-]', '_', filename)

def download_pdf_requests(url):
    """Attempt to download a PDF using requests."""
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200 and 'application/pdf' in response.headers.get("Content-Type", ""):
            return response.content
        else:
            logging.error(f"Primary download failed for {url}: status {response.status_code} or invalid content type.")
    except Exception as e:
        logging.error(f"Exception during primary download from {url}: {e}")
    return None

def download_pdf_pypaperbot(doi):
    """
    Download PDF using PyPaperBot as a backup strategy.
    Writes the DOI to a temporary file, calls PyPaperBot via subprocess,
    and returns the PDF content if found.
    """
    logging.info(f"Attempting backup download via PyPaperBot for DOI {doi}")
    temp_doi_file_path = None
    temp_dir = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_doi_file:
            temp_doi_file.write(doi)
            temp_doi_file_path = temp_doi_file.name
        temp_dir = tempfile.mkdtemp()
        command = [
            "python", "-m", "PyPaperBot",
            "--doi-file", temp_doi_file_path,
            "--dwn-dir", temp_dir
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            pdf_files = glob.glob(os.path.join(temp_dir, "*.pdf"))
            if pdf_files:
                pdf_path = pdf_files[0]
                with open(pdf_path, "rb") as f:
                    pdf_content = f.read()
                return pdf_content
            else:
                logging.error(f"PyPaperBot did not download any PDF for DOI {doi}")
        else:
            logging.error(f"PyPaperBot subprocess failed for DOI {doi} with error: {result.stderr}")
    except Exception as e:
        logging.error(f"Exception during backup download via PyPaperBot for DOI {doi}: {e}")
    finally:
        if temp_doi_file_path and os.path.exists(temp_doi_file_path):
            try:
                os.remove(temp_doi_file_path)
            except Exception:
                pass
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
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

def remove_doi_prefix(doi):
    """Remove 'https://doi.org/' or 'doi:' prefixes from a DOI."""
    return doi.replace("https://doi.org/", "").replace("doi:", "").strip()

def process_citation_graph(citation_graph_file, output_dir, grobid_url):
    grobid_url = test_grobid_api(grobid_url)
    try:
        with open(citation_graph_file, "r", encoding="utf-8") as jf:
            citation_graph = json.load(jf)
    except Exception as e:
        logging.error(f"Error loading citation graph file {citation_graph_file}: {e}")
        exit(1)

    for key, records in citation_graph.items():
        logging.info(f"Processing cited article: {key}")
        sanitized_key = sanitize_filename(key)
        article_folder = os.path.join(output_dir, sanitized_key)
        pdf_folder = os.path.join(article_folder, "PDF")
        tei_folder = os.path.join(article_folder, "TEI")
        os.makedirs(pdf_folder, exist_ok=True)
        os.makedirs(tei_folder, exist_ok=True)

        for record in records.get("openalex", []):
            doi_val = record.get("doi", "").strip()
            if not doi_val:
                record["forward_dl_filename"] = ""
                continue
            base_filename = sanitize_filename(remove_doi_prefix(doi_val))
            pdf_path = os.path.join(pdf_folder, f"{base_filename}.pdf")
            retrievable = record.get("pdf_url") or ""
            pdf_content = None
            if retrievable.startswith("http"):
                logging.info(f"Attempting primary download for {doi_val} from {retrievable}")
                pdf_content = download_pdf_requests(retrievable)
            if not pdf_content:
                pdf_content = download_pdf_pypaperbot(remove_doi_prefix(doi_val))
            if pdf_content:
                try:
                    with open(pdf_path, "wb") as pf:
                        pf.write(pdf_content)
                    logging.info(f"Saved PDF for {doi_val} as {pdf_path}")
                    tei_xml = process_pdf_with_grobid(pdf_path, grobid_url, tei_folder)
                    record["forward_dl_filename"] = base_filename if tei_xml else ""
                except Exception as e:
                    logging.error(f"Error saving PDF for {doi_val}: {e}")
                    record["forward_dl_filename"] = ""
            else:
                logging.error(f"Failed to download PDF for {doi_val}")
                record["forward_dl_filename"] = ""
            time.sleep(random.uniform(3, 7))
        
        scholarly_extra_list = records.get("scholarly_extra", [])
        new_extra = []
        for doi_val in scholarly_extra_list:
            doi_val = doi_val.strip()
            if not doi_val:
                new_extra.append({"doi": "", "forward_dl_filename": ""})
                continue
            base_filename = sanitize_filename(remove_doi_prefix(doi_val))
            pdf_path = os.path.join(pdf_folder, f"{base_filename}.pdf")
            pdf_content = download_pdf_pypaperbot(remove_doi_prefix(doi_val))
            if pdf_content:
                try:
                    with open(pdf_path, "wb") as pf:
                        pf.write(pdf_content)
                    logging.info(f"Saved PDF for scholarly extra {doi_val} as {pdf_path}")
                    tei_xml = process_pdf_with_grobid(pdf_path, grobid_url, tei_folder)
                    dl_filename = base_filename if tei_xml else ""
                except Exception as e:
                    logging.error(f"Error saving PDF for scholarly extra {doi_val}: {e}")
                    dl_filename = ""
            else:
                logging.error(f"Failed to download PDF for scholarly extra {doi_val}")
                dl_filename = ""
            new_extra.append({"doi": doi_val, "forward_dl_filename": dl_filename})
            time.sleep(random.uniform(3, 7))
        records["scholarly_extra"] = new_extra
        time.sleep(random.uniform(10, 20))
    
    updated_json_path = os.path.join(output_dir, "citation_graph_updated.json")
    try:
        with open(updated_json_path, "w", encoding="utf-8") as outjf:
            json.dump(citation_graph, outjf, indent=4)
        logging.info(f"Updated citation graph saved to {updated_json_path}")
    except Exception as e:
        logging.error(f"Error writing updated citation graph: {e}")

def main():
    parser = argparse.ArgumentParser(description="Download PDFs for forward citations and process via Grobid.")
    parser.add_argument("-j", "--json", required=True, help="Path to citation_graph.json file.")
    parser.add_argument("-p", "--grobid", default="http://127.0.0.1:8070", help="Grobid API URL (e.g., http://127.0.0.1:8070).")
    parser.add_argument("-o", "--output", default="/home/tamas002/aistuff/citation-checker-poc/forward_citation_searches/metadata", help="Output base folder (default: /home/tamas002/aistuff/citation-checker-poc/forward_citation_searches/metadata).")
    args = parser.parse_args()
    
    process_citation_graph(args.json, args.output, args.grobid)

if __name__ == "__main__":
    main()
