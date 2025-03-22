# Integrated PDF Citation Verification Workflow

This repository is an integrated workflow for verifying the consistency and integrity of citations within and across academic records. The workflow is designed to:

- **Extract bibliographic and in-text citation data** from PDFs.
- **Match in-text citations to bibliography entries**.
- **Verify DOI presence** of bibliography items.
- **Test existence of DOI indicated record** and download when available.
- **Compare citing sentences to cited articles** using NLI models to test for support.
- **Capture the decisions made** in a JSON log to a) train NLI models, b) document integrity of the academic record.

## Overview

The workflow is composed of several modules that work together in a sequential pipeline:

1. **Data Extraction**:  
   - **grobid-folder.py**: Parses academic PDFs into tei.xml.  
     *Processes PDF files in a specified folder using the Grobid API. For each PDF file found in the folder, the script sends the file to the Grobid API endpoint and retrieves the corresponding TEI XML which is saved in a new subfolder  /tei.*

2. **Citation Matching**:  
   - **match-cit-to-bib.py**: Tests match between in-text citations and bibliography items.  
     *Produces a .json file in a new folder /match-cit-bib from each tei.xml in /tei and creates a summary .csv placed in project home.*

3. **Result Consolidation**:  
   - **consolidate.py**: Consolidates bibliography items for each tei.xml file in /tei and then tests if records exist. 
     *Extracts bibliographic records, queries Crossref for a DOI using and related metadata using a fuzzy match, checks for the retrievability of the record using OpenAlex, Unpaywall, and a a HEAD request. Output is saved in /consolidation in detailed (.json) and summary (.csv) form.*

4. **DOI Verification and Article Retrieval**:  
   - **retrieve.py**: Retrieves records found to be downloadable.  
     *Uses .json files from step 3 to download retrievable records, renames to sanitized doi, saves the pdf to /citing_filename/PDF and converted to /citing_filename/tei.*

5. **Contextual Verification**:  
   - **match-citing-to-cited.py**: Matches citing sentences to cited articles.  
     *Savels a .csv in /citing_article_filename listing citing sentences and the corresponding filenames (sanitized doi) of retrieved cited records.*

6. **Entailment Checking**
   - **nli-checking.py**: Uses Natural Language Inference (NLI) to evaluate whether there is entailing content in the cited record for the citing sentence.   
     *Gradio interface. Requires pasting the citing sentence, editing for consistency with NLI expectations, pasting of full text of TEI, model selection and rolling window size selection.*
   - **nli-checking-extended.py**: Same as above with contradiction, logging to support fine tuning and a UI to support testing NLI model performance.


## Integrated Workflow Explanation

The entire workflow operates as a cohesive, integrated pipeline:

1. **PDF Input**:  
   - Start with one or more PDFs that need to be verified.

2. **Data Extraction**:  
   - Run **grobid-folder.py** to extract both bibliographic entries and in-text citation markers from the PDFs.

3. **Citation Matching**:  
   - Execute **match-cit-to-bib.py** to ensure that each in-text citation corresponds to an entry in the bibliography.

4. **Result Consolidation**:  
   - Use, **consolidate.py** to get DOIs for bib items.

5. **DOI Verification and Retrieval**:  
   - Use **retrieve.py** to retrieve bib items

6. **Match citing sentences to cited records**:  
   - Run **match-citing-to-cited.py**
  
7. **Check entailment**
   - Run **nli-checking(-extended).py** to iterate through citing sentences to see if there is supporting assertions in the cited records 


## Usage Instructions

NOTE: requires access to GROBID

1. **Clone the Repository**:
    ```bash
    git clone https://github.com/yourusername/your-repo-name.git
    cd your-repo-name
    ```

2. **Install Dependencies**:  
    ```bash
    pip install -r requirements.txt
    ```

4. **Run the Workflow**:
   see documentation in each script for details  

