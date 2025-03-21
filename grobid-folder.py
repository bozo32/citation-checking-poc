
import os
import glob
import requests
import logging
import argparse
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def process_pdf_with_grobid(pdf_path, grobid_url, output_dir=None):
    """
    Send a PDF file to the Grobid API and return the TEI XML.
    If an output_dir is provided, the TEI XML is saved there.
    
    Adapted from the original gradio-3.py implementation (Peter, 2025).
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
                logging.info(f"Grobid processing succeeded for {pdf_path}.")
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)
                    tei_filename = os.path.splitext(os.path.basename(pdf_path))[0] + ".tei.xml"
                    tei_output_path = os.path.join(output_dir, tei_filename)
                    with open(tei_output_path, "w", encoding="utf-8") as f_out:
                        f_out.write(tei_xml)
                    logging.info(f"TEI XML saved to {tei_output_path}.")
                return tei_xml
            else:
                logging.error(f"Grobid failed for {pdf_path} with status {response.status_code}.")
    except Exception as e:
        logging.error(f"Exception processing {pdf_path}: {e}")
    return None

def process_folder(folder, grobid_url):
    """
    Process all PDF files in the specified folder (case-insensitive).
    The resulting TEI XML files are saved in a new subfolder 'tei' within the folder.
    
    Note: Existing TEI files in the 'tei' folder may be overwritten.
    """
    output_folder = os.path.join(folder, "tei")
    os.makedirs(output_folder, exist_ok=True)
    # Use a case-insensitive pattern to find PDFs
    pdf_files = [f for f in glob.glob(os.path.join(folder, "*"))
                 if re.search(r'\.pdf$', f, re.IGNORECASE)]
    if not pdf_files:
        logging.info("No PDF files found in the folder.")
        return
    for pdf_file in pdf_files:
        logging.info(f"Processing {pdf_file}...")
        process_pdf_with_grobid(pdf_file, grobid_url, output_dir=output_folder)
    logging.info("Processing complete.")

def main():
    parser = argparse.ArgumentParser(description="Process PDFs in a folder using the Grobid API.")
    parser.add_argument('-f', '--folder', required=True, help="Folder containing PDF files.")
    parser.add_argument('-p', '--grobid_url', required=True, help="Grobid API URL.")
    args = parser.parse_args()
    
    if not os.path.isdir(args.folder):
        logging.error(f"The folder {args.folder} does not exist or is not a directory.")
        return
    
    process_folder(args.folder, args.grobid_url)

if __name__ == "__main__":
    main()

"""
Grobid-Folder Script Documentation
------------------------------

Overview:
---------
The script "grobid-folder.py" processes PDF files in a specified folder using the Grobid API. For each PDF file found in the folder, the script sends the file to the Grobid API endpoint and retrieves the corresponding TEI XML output. The output is then saved in a new subfolder named "tei" within the input folder.

Requirements:
-------------
- Python 3.x installed on your system.
- The following Python modules must be available: os, glob, requests, logging, argparse, and re.
- Access to a running Grobid API instance. The API URL must be provided as a command-line argument.
- A folder containing PDF files (with extensions matching .pdf, case-insensitive).

Usage:
------
Run the script from the command line using the following syntax:

    python grobid-folder.py -f <folder_directory> -p <grobid_API_url>

Example:
    python grobid-folder.py -f /path/to/pdf_folder -p http://localhost:8070/api/processFulltextDocument

Default Parameters:
-------------------
Within the script, the following parameters are sent in the POST request to the Grobid API:

    consolidateHeader      : '1'
    consolidateCitations   : '1'
    includeRawAffiliations : '1'
    includeRawCitations    : '1'
    segmentSentences       : '1'

These parameters instruct the Grobid API to:
- Consolidate header information from the PDF.
- Consolidate citation information.
- Include raw affiliation data.
- Include raw citation data.
- Segment the text into sentences.

Output:
-------
- The script creates a subfolder named "tei" within the specified folder (if it does not already exist).
- For each PDF file processed, a TEI XML file is generated with the same base name as the PDF and a ".tei.xml" extension.

Logging and Error Handling:
---------------------------
- Logging is configured to display messages at the INFO level to provide feedback during processing.
- If the provided folder does not exist or contains no PDF files, the script logs an appropriate message.
- Any errors encountered during the processing of a PDF (such as connection issues with the Grobid API) are logged as errors.

Customization:
--------------
If necessary, you can modify the default parameters in the function process_pdf_with_grobid to suit your requirements.

Contact / Support:
------------------
For further assistance or to report issues, please refer to the comments within the script or contact the developer.

------------------------------
End of Documentation
------------------------------
"""
