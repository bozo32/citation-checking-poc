#!/usr/bin/env python3
import os
import glob
import csv
import json
import logging
import requests
import argparse
from bs4 import BeautifulSoup
from fuzzywuzzy import fuzz
#from scholarly import scholarly  # Scholarly fallback is commented out to avoid captcha issues

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# --- Similarity thresholds ---
DEFAULT_THRESHOLD = 0.9
FIELD_THRESHOLDS = {
    "author": 0.85,    # slightly lower given name variations
    "title": 0.85,
    "year": 1.0,       # require exact match for year
    "publisher": 0.9
}

def compare_authors(tei_authors, cross_authors, threshold):
    token_score = fuzz.token_set_ratio(tei_authors, cross_authors) / 100.0
    tei_list = set(a.strip().lower() for a in tei_authors.split(",") if a.strip())
    cross_list = set(a.strip().lower() for a in cross_authors.split(",") if a.strip())
    if not tei_list or not cross_list:
        return 1.0
    intersection = tei_list.intersection(cross_list)
    union = tei_list.union(cross_list)
    jaccard = len(intersection) / len(union)
    weighted_score = 0.7 * token_score + 0.3 * jaccard
    return weighted_score

def compare_bib_entries(tei_bib, crossref_bib, default_threshold=DEFAULT_THRESHOLD, field_thresholds=FIELD_THRESHOLDS):
    conflicting = {}
    for field in ["author", "title", "year", "publisher"]:
        tei_value = tei_bib.get(field, "").strip()
        cross_value = crossref_bib.get(field, "").strip()
        if not tei_value or not cross_value:
            continue
        if field == "author":
            similarity = compare_authors(tei_value, cross_value, field_thresholds.get(field, default_threshold))
        else:
            similarity = fuzz.ratio(tei_value.lower(), cross_value.lower()) / 100.0
        threshold = field_thresholds.get(field, default_threshold)
        if similarity < threshold:
            conflicting[field] = {"tei": tei_value, "crossref": cross_value, "similarity": similarity}
    return conflicting

def dict_to_bibtex(bib_dict, bib_item, entry_type="article"):
    fields = []
    for key, value in bib_dict.items():
        if value:
            safe_value = value.replace("{", "\\{").replace("}", "\\}")
            fields.append(f"  {key} = {{{safe_value}}}")
    fields_str = ",\n".join(fields)
    return f"@{entry_type}{{{bib_item},\n{fields_str}\n}}"

def find_crossref_doi(ref_info):
    params = {}
    if ref_info.get("author"):
        params["query.author"] = ref_info["author"]
    if ref_info.get("title"):
        params["query.title"] = ref_info["title"]
    if ref_info.get("year"):
        year = ref_info["year"]
        params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"
    params["rows"] = 1
    email = CrossrefMailto.split("mailto:")[1] if "mailto:" in CrossrefMailto else CrossrefMailto
    params["mailto"] = email
    url = "https://api.crossref.org/works"
    logging.debug(f"Querying Crossref with parameters: {params}")
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            items = response.json().get("message", {}).get("items", [])
            if items:
                doi = items[0].get("DOI")
                logging.info(f"Crossref DOI found: {doi} for query: {params}")
                return doi
        else:
            logging.error(f"Crossref API error: {response.status_code}")
    except Exception as e:
        logging.error(f"Error querying Crossref: {e}")
    return None

def check_openalex(doi):
    url = f"https://api.openalex.org/works/doi:{doi}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            oa_info = data.get("open_access", {})
            if oa_info.get("is_oa") and oa_info.get("oa_url"):
                return oa_info.get("oa_url")
    except Exception as e:
        logging.error(f"Error querying OpenAlex for DOI {doi}: {e}")
    return None

def check_doi_retrievability(doi, flat_tei):
    # Step 1: Try OpenAlex
    oa_url = check_openalex(doi)
    if oa_url:
        return oa_url
    # Step 2: Try Unpaywall
    email = CrossrefMailto.split("mailto:")[1] if "mailto:" in CrossrefMailto else CrossrefMailto
    unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
    try:
        resp = requests.get(unpaywall_url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            best = data.get("best_oa_location")
            if best:
                if best.get("url_for_pdf"):
                    return best.get("url_for_pdf")
                elif best.get("url"):
                    return best.get("url")
    except Exception as e:
        logging.error(f"Error checking Unpaywall for DOI {doi}: {e}")
    # Scholarly fallback is commented out to avoid captcha issues.
    # Final fallback: HEAD request to DOI resolver
    doi_url = f"https://doi.org/{doi}"
    try:
        resp = requests.head(doi_url, allow_redirects=True, timeout=10)
        if resp.status_code == 200:
            return "yes"
        else:
            return "no"
    except Exception as e:
        logging.error(f"Error performing HEAD request for DOI {doi}: {e}")
        return "no"

def extract_tei_bibl_struct(bibl):
    analytic_dict = {}
    analytic = bibl.find("analytic")
    if analytic:
        title_tag = analytic.find("title", {"type": "main"})
        if not title_tag:
            title_tag = analytic.find("title")
        if title_tag:
            analytic_dict["title"] = title_tag.get_text(strip=True)
        authors = []
        for author in analytic.find_all("author"):
            pers = author.find("persName")
            if pers:
                forename = pers.find("forename")
                surname = pers.find("surname")
                if forename and surname:
                    authors.append(f"{forename.get_text(strip=True)} {surname.get_text(strip=True)}")
                else:
                    authors.append(pers.get_text(strip=True))
            else:
                authors.append(author.get_text(strip=True))
        if authors:
            analytic_dict["authors"] = authors
        idno = analytic.find("idno", {"type": "DOI"})
        if idno:
            analytic_dict["doi"] = idno.get_text(strip=True)
    
    monogr_dict = {}
    monogr = bibl.find("monogr")
    if monogr:
        titles = monogr.find_all("title")
        for t in titles:
            if t.get("type") == "abbrev":
                monogr_dict["abbrev_title"] = t.get_text(strip=True)
            else:
                monogr_dict["title"] = t.get_text(strip=True)
        if not analytic_dict.get("authors"):
            authors = []
            for author in monogr.find_all("author"):
                pers = author.find("persName")
                if pers:
                    forename = pers.find("forename")
                    surname = pers.find("surname")
                    if forename and surname:
                        authors.append(f"{forename.get_text(strip=True)} {surname.get_text(strip=True)}")
                    else:
                        authors.append(pers.get_text(strip=True))
                else:
                    authors.append(author.get_text(strip=True))
            if authors:
                monogr_dict["authors"] = authors
        idno_issn = monogr.find("idno", {"type": "ISSN"})
        if idno_issn:
            monogr_dict["issn"] = idno_issn.get_text(strip=True)
        idno_issne = monogr.find("idno", {"type": "ISSNe"})
        if idno_issne:
            monogr_dict["issne"] = idno_issne.get_text(strip=True)
        imprint = monogr.find("imprint")
        if imprint:
            imprint_dict = {}
            vol = imprint.find("biblScope", {"unit": "volume"})
            if vol:
                imprint_dict["volume"] = vol.get_text(strip=True)
            issue = imprint.find("biblScope", {"unit": "issue"})
            if issue:
                imprint_dict["issue"] = issue.get_text(strip=True)
            page = imprint.find("biblScope", {"unit": "page"})
            if page:
                from_page = page.get("from")
                to_page = page.get("to")
                if from_page and to_page:
                    imprint_dict["pages"] = f"{from_page}-{to_page}"
                elif from_page:
                    imprint_dict["pages"] = from_page
            date_tag = imprint.find("date", {"type": "published"})
            if date_tag:
                imprint_dict["date"] = date_tag.get("when", "").strip()
            publisher_tag = imprint.find("publisher")
            if publisher_tag:
                imprint_dict["publisher"] = publisher_tag.get_text(strip=True)
            if imprint_dict:
                monogr_dict["imprint"] = imprint_dict
    return {"analytic": analytic_dict, "monogr": monogr_dict}

def flatten_tei_bibl(tei_struct):
    flat = {}
    analytic = tei_struct.get("analytic", {})
    monogr = tei_struct.get("monogr", {})
    authors = analytic.get("authors", []) or monogr.get("authors", [])
    if authors:
        flat["author"] = ", ".join(authors)
    title = analytic.get("title", "") or monogr.get("title", "")
    flat["title"] = title
    imprint = monogr.get("imprint", {})
    if imprint.get("date"):
        flat["year"] = imprint.get("date")
    if imprint.get("publisher"):
        flat["publisher"] = imprint.get("publisher")
    return flat

def extract_crossref_bib(doi):
    url = f"https://api.crossref.org/works/{doi}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            message = response.json().get("message", {})
            authors = []
            for a in message.get("author", []):
                given = a.get("given", "")
                family = a.get("family", "")
                name = " ".join([given, family]).strip()
                if name:
                    authors.append(name)
            author_str = ", ".join(authors)
            year = ""
            issued = message.get("issued", {})
            if "date-parts" in issued and issued["date-parts"]:
                year = str(issued["date-parts"][0][0])
            title = ""
            titles = message.get("title", [])
            if titles:
                title = titles[0]
            publisher = message.get("publisher", "")
            return {"author": author_str, "year": year, "title": title, "publisher": publisher}
    except Exception as e:
        logging.error(f"Error retrieving Crossref metadata for DOI {doi}: {e}")
    return {}

def format_bib_entry(bib):
    parts = []
    if bib.get("author"):
        parts.append(bib["author"])
    if bib.get("year"):
        parts.append(f"({bib['year']})")
    if bib.get("title"):
        parts.append(bib["title"])
    if bib.get("publisher"):
        parts.append(bib["publisher"])
    return ", ".join(parts)

def check_doi_retrievability(doi, flat_tei):
    # Step 1: Try OpenAlex
    oa_url = check_openalex(doi)
    if oa_url:
        return oa_url
    # Step 2: Try Unpaywall
    email = CrossrefMailto.split("mailto:")[1] if "mailto:" in CrossrefMailto else CrossrefMailto
    unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
    try:
        resp = requests.get(unpaywall_url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            best = data.get("best_oa_location")
            if best:
                if best.get("url_for_pdf"):
                    return best.get("url_for_pdf")
                elif best.get("url"):
                    return best.get("url")
    except Exception as e:
        logging.error(f"Error checking Unpaywall for DOI {doi}: {e}")
    # Scholarly fallback is commented out due to captcha issues.
    # Final Fallback: Use HEAD request to DOI resolver
    doi_url = f"https://doi.org/{doi}"
    try:
        resp = requests.head(doi_url, allow_redirects=True, timeout=10)
        if resp.status_code == 200:
            return "yes"
        else:
            return "no"
    except Exception as e:
        logging.error(f"Error performing HEAD request for DOI {doi}: {e}")
        return "no"

def process_tei_file(tei_file_path, consolidation_folder):
    try:
        with open(tei_file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logging.error(f"Error reading {tei_file_path}: {e}")
        return

    soup = BeautifulSoup(content, "xml")
    bibl_structs = soup.find_all("biblStruct")
    if not bibl_structs:
        logging.info(f"No <biblStruct> found in {tei_file_path}")
        return

    records = []
    csv_rows = []
    for bibl in bibl_structs:
        bib_item = bibl.get("xml:id", "")
        tei_struct = extract_tei_bibl_struct(bibl)
        flat_tei = flatten_tei_bibl(tei_struct)
        source_doi = tei_struct.get("analytic", {}).get("doi", "")
        crossref_doi = find_crossref_doi(flat_tei)
        crossref_bib = extract_crossref_bib(crossref_doi) if crossref_doi else {}
        conflicts = compare_bib_entries(flat_tei, crossref_bib)
        tei_formatted = format_bib_entry(flat_tei)
        crossref_formatted = format_bib_entry(crossref_bib) if crossref_bib else ""
        tei_bib_tex = dict_to_bibtex(flat_tei, bib_item, entry_type="article")
        crossref_bib_tex = dict_to_bibtex(crossref_bib, bib_item, entry_type="article") if crossref_bib else ""
        retrieval = ""
        if crossref_doi:
            retrieval = check_doi_retrievability(crossref_doi, flat_tei)
        else:
            # Final fallback using scholarly search based on flat_tei (including year)
            query = ""
            if flat_tei.get("author"):
                query += flat_tei["author"] + " "
            if flat_tei.get("title"):
                query += flat_tei["title"] + " "
            if flat_tei.get("year"):
                query += flat_tei["year"]
            try:
                # Scholarly fallback is disabled to avoid captcha issues; code left for reference.
                # search_query = scholarly.search_pubs(query)
                # pub = next(search_query, None)
                # if pub:
                #     pub = scholarly.fill(pub)
                #     if "eprint_url" in pub and pub["eprint_url"]:
                #         retrieval = pub["eprint_url"]
                #     else:
                #         retrieval = "yes"
                # else:
                #     retrieval = "no"
                retrieval = "no"
            except Exception as e:
                logging.error(f"Error in final scholarly fallback for query '{query}': {e}")
                retrieval = "no"
        record = {
            "bib_item": bib_item,
            "tei": {
                "structure": tei_struct,
                "flat": flat_tei,
                "bibtex": tei_bib_tex
            },
            "crossref": {
                "fields": crossref_bib,
                "bibtex": crossref_bib_tex
            },
            "tei_formatted": tei_formatted,
            "crossref_formatted": crossref_formatted,
            "source_doi": source_doi,
            "crossref_doi": crossref_doi if crossref_doi else "",
            "conflicting_fields": conflicts,
            "retrievable": retrieval
        }
        records.append(record)
        conflict_fields = ", ".join(conflicts.keys())
        csv_rows.append({
            "bib_item": bib_item,
            "tei_bib": tei_formatted,
            "crossref_bib": crossref_formatted,
            "conflicting_fields": conflict_fields,
            "retrievable": retrieval
        })

    base_name = os.path.splitext(os.path.basename(tei_file_path))[0]
    os.makedirs(consolidation_folder, exist_ok=True)
    json_filename = base_name + "-crossref.json"
    json_filepath = os.path.join(consolidation_folder, json_filename)
    try:
        with open(json_filepath, "w", encoding="utf-8") as jf:
            json.dump(records, jf, indent=4)
        logging.info(f"JSON file saved: {json_filepath}")
    except Exception as e:
        logging.error(f"Error writing JSON file {json_filepath}: {e}")

    csv_filename = base_name + "-crossref.csv"
    csv_filepath = os.path.join(consolidation_folder, csv_filename)
    try:
        with open(csv_filepath, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["bib_item", "tei_bib", "crossref_bib", "conflicting_fields", "retrievable"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in csv_rows:
                writer.writerow(row)
        logging.info(f"CSV file saved: {csv_filepath}")
    except Exception as e:
        logging.error(f"Error writing CSV file {csv_filepath}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Consolidate Crossref and TEI bibliographic data.")
    parser.add_argument("-f", "--folder", required=True,
                        help="Full path to the project home directory (TEI files are expected in <folder>/tei).")
    parser.add_argument("-u", "--user", required=True,
                        help="User email address (used for Crossref and Unpaywall API calls).")
    args = parser.parse_args()
    global CrossrefMailto
    CrossrefMailto = f"mailto:{args.user}"
    project_home = args.folder
    tei_folder = os.path.join(project_home, "tei")
    consolidation_folder = os.path.join(project_home, "consolidation")
    tei_files = glob.glob(os.path.join(tei_folder, "*.tei.xml"))
    if not tei_files:
        logging.info(f"No TEI files found in folder '{tei_folder}'.")
        return
    for tei_file in tei_files:
        process_tei_file(tei_file, consolidation_folder)

if __name__ == "__main__":
    main()

"""
Consolidate Script Documentation
------------------------------

Overview:
---------
The script "consolidate.py" processes TEI XML files in a specified project home directory by consolidating bibliographic data from the TEI files with metadata retrieved from Crossref, Unpaywall, and OpenAlex. For each TEI file found in the <project_home>/tei folder, the script extracts bibliographic records (from the TEI <biblStruct> elements), constructs a simplified (flattened) record, and queries Crossref for a DOI and related metadata. It then checks for the retrievability of the record using a sequence of services (OpenAlex, Unpaywall, and a final fallback using a HEAD request). The output is saved both as a detailed JSON file and as a summary CSV file in a subfolder named "consolidation" within the project home directory.

Requirements:
-------------
- Python 3.x installed on your system.
- The following Python modules must be available: os, glob, csv, json, logging, requests, argparse, bs4 (BeautifulSoup), and fuzzywuzzy.
- A valid email address to be used with the Crossref and Unpaywall APIs.
- A folder containing TEI XML files in a subfolder named "tei" within the specified project home directory.
- An Internet connection to access Crossref, Unpaywall, and OpenAlex APIs.

Usage:
------
Run the script from the command line using the following syntax:

    python consolidate_crossref.py -f <project_home_directory> -u <user_email>

Example:
    python consolidate_crossref.py -f /path/to/project_home -u user@example.com

Default Parameters:
-------------------
Within the script, the following similarity thresholds are defined for comparing bibliographic fields:
- DEFAULT_THRESHOLD: 0.9 (90% similarity required by default)
- FIELD_THRESHOLDS:
    - author    : 0.85 (allows slight variations in author names)
    - title     : 0.85
    - year      : 1.0  (exact match required)
    - publisher : 0.9

When querying Crossref, the script uses a constructed query from the flattened TEI record by including the author(s), title, and publication year. The script also uses the following retrievability-check sequence:
1. OpenAlex: If OpenAlex returns an open-access URL, that URL is used.
2. Unpaywall: If Unpaywall returns an OA URL (using the provided user email), that URL is used.
3. If none of these yield a downloadable URL, a final fallback uses an HTTP HEAD request to the DOI resolver to confirm whether the DOI resolves (returning "yes" or "no").

Output:
-------
- The script creates a subfolder named "consolidation" within the project home directory (if it does not already exist).
- For each TEI file processed (found in <project_home>/tei), the script generates:
  - A detailed JSON file named "<tei_filename>-crossref.json" containing an array of records for each bibliographic item. Each record includes:
      - The full TEI structure (analytic and monogr) and a flattened version.
      - The corresponding Crossref metadata (if available), with both structured fields and a BibTeX-formatted entry.
      - A field "conflicting_fields" that lists any fields (author, title, year, publisher) where the TEI and Crossref records differ beyond the set thresholds.
      - A "retrievable" field indicating the result of the retrieval check (an OA URL, "yes", or "no").
  - A CSV summary file named "<tei_filename>-crossref.csv" with columns:
      - bib_item (the identifier from the TEI record)
      - tei_bib (an APA-style formatted string from the TEI data)
      - crossref_bib (an APA-style formatted string from Crossref data)
      - conflicting_fields (a comma-separated list of fields where discrepancies were found)
      - retrievable (the retrieval result as described above)

Logging and Error Handling:
---------------------------
- Logging is configured to display messages at the INFO level, providing feedback on the progress of file processing and API calls.
- If the provided project home directory or its subfolder "tei" does not exist or contains no TEI files, the script logs an appropriate message.
- Any errors encountered during file reading, API requests, or processing (e.g., connection issues) are logged as errors.

Customization:
--------------
- You may adjust the similarity thresholds in the FIELD_THRESHOLDS dictionary to fine-tune the matching of bibliographic fields.
- The script uses a flattened version of the TEI bibliographic record. You can modify the flatten_tei_bibl() function if your TEI structure changes.
- The retrieval check sequence (OpenAlex → Unpaywall → HEAD request) can be further modified if you wish to integrate additional services.
- The scholarly fallback code remains commented out to avoid triggering captchas on Google Scholar. If you later decide to use it, be aware of potential legal and technical issues.

Contact / Support:
------------------
For further assistance or to report issues, please refer to the inline comments within the script or contact the developer.

------------------------------
End of Documentation
------------------------------
"""