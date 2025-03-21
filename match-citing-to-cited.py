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