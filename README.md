# Integrated PDF Citation Verification Workflow

This repository is an integrated workflow for verifying the consistency and integrity of citations within and across academic records. The workflow is designed to:

- **Extract bibliographic and in-text citation data** from PDFs.
- **Match in-text citations to bibliography entries**.
- **Verify DOI presence** of bibliography items.
- **Validate DOI existence** and download corresponding records when available.
- **Compare citing sentences against cited articles** using NLI models to test that citing claims are correctly supported.
- - **Generate training data for NLI models** Capture the decisions made by users in a JSON log.

## Overview

The workflow is composed of several modules that work together in a sequential pipeline:

1. **Data Extraction**:  
   - **grobid-folder.py**: Extracts structured bibliographic information and in-text citation markers from PDFs using GROBID.  
     *Embedded documentation notes that this module standardizes the citation data for further analysis.*

2. **Citation Matching**:  
   - **match-cit-to-bib.py**: Ensures that every in-text citation found in the document has a corresponding entry in the bibliography.  
     *The module’s embedded documentation describes its method for flagging mismatches.*

3. **Result Consolidation**:  
   - **consolidate.py**: Uses Unpaywall, Crossref and OpenAlex to try and match bibliography items to DOIs. 
     *If unpaywall reports a link, it records the link.*

4. **DOI Verification and Article Retrieval**:  
   - **retrieve.py**: Checks each bibliography item to see if the DOI points to a record that exists.  
     *Uses head from Crossref and Unpaywall. Has script for google scholar commented out*

5. **Contextual Verification**:  
   - **match-citing-to-cited.py**: Matches citing sentences from the PDF with content from the cited articles.  
     *Produces a CSV that lists citation id, citing sentence text and cited article filename.*

6. **Entailment Checking**
   - **nli-checking.py**: Uses Natural Language Inference (NLI) to evaluate whether there is supporting content in the cited record for the citing sentence.   
     *Gradio interface. Requires pasting the citing sentence, editing for consistency with NLI expectations, pasting of full text of TEI, model selection and rolling window size selection.*
   - **nli-checking-extended.py**: Uses Natural Language Inference (NLI) to evaluate whether there is supporting content in the cited record for the citing sentence.   
     *same as above with logging, contradiction and a framework to test the performance of NLI models*


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

1. **Clone the Repository**:
    ```bash
    git clone https://github.com/yourusername/your-repo-name.git
    cd your-repo-name
    ```

2. **Install Dependencies**:  
   requirements.txt
   Access to a GROBID API

4. **Run the Workflow**:
   see documentation in each script for details  

