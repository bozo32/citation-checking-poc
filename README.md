# Integrated PDF Citation Verification Workflow

This repository implements an integrated workflow for verifying the consistency and integrity of citations in PDF documents. The workflow is designed to:

- **Extract bibliographic and in-text citation data** from PDFs.
- **Match in-text citations to bibliography entries**.
- **Verify DOI presence** in bibliography items.
- **Validate DOI existence** and download corresponding articles when available.
- **Compare citing sentences against cited articles** to ensure that the context of citations is accurate.

## Overview

The workflow is composed of several modules that work together in a sequential pipeline:

1. **Data Extraction**:  
   - **grobid-folder.py**: Extracts structured bibliographic information and in-text citation markers from PDFs using GROBID.  
     *Embedded documentation notes that this module standardizes the citation data for further analysis.*

2. **Citation Matching**:  
   - **match-cit-to-bib.py**: Ensures that every in-text citation found in the document has a corresponding entry in the bibliography.  
     *The module’s embedded documentation describes its method for flagging mismatches.*

3. **DOI Verification and Article Retrieval**:  
   - **retrieve.py**: Checks each bibliography item for a DOI, verifies its validity, and downloads the corresponding article if available.  
     *According to its documentation, error handling is built in to manage missing or invalid DOIs.*

4. **Contextual Verification**:  
   - **match-citing-to-cited.py**: Matches citing sentences from the PDF with content from the cited articles.  
     *The embedded documentation explains that this step confirms the proper use of citations.*  
   - **nli-checking.py**: Uses Natural Language Inference (NLI) to evaluate whether the semantic content of the citing sentences aligns with the cited material.  
     *This module’s documentation details its role in deep contextual verification.*

5. **Result Consolidation**:  
   - **consolidate.py**: Aggregates outputs from the previous modules into a comprehensive report, highlighting mismatches, missing DOIs, or semantic discrepancies.  
     *The final module’s documentation underscores its role in compiling all results for review.*

## Integrated Workflow Explanation

The entire workflow operates as a cohesive, integrated pipeline:

1. **PDF Input**:  
   - Start with one or more PDFs that need to be verified.

2. **Data Extraction**:  
   - Run **grobid-folder.py** to extract both bibliographic entries and in-text citation markers from the PDFs.

3. **Citation Matching**:  
   - Execute **match-cit-to-bib.py** to ensure that each in-text citation corresponds to an entry in the bibliography.

4. **DOI Verification and Retrieval**:  
   - Use **retrieve.py** to examine bibliography items for DOIs. This module checks DOI validity and downloads the associated articles when possible, handling any errors (e.g., missing or invalid DOIs) as specified in its embedded documentation.

5. **Contextual Analysis**:  
   - Run **match-citing-to-cited.py** and **nli-checking.py** to compare the citing sentences against the downloaded articles, confirming that the citation context is accurate.

6. **Result Consolidation**:  
   - Finally, **consolidate.py** collects all the outputs and generates a final report that summarizes the verification process, detailing any discrepancies or issues.

## Usage Instructions

1. **Clone the Repository**:
    ```bash
    git clone https://github.com/yourusername/your-repo-name.git
    cd your-repo-name
    ```

2. **Install Dependencies**:  
   Follow the instructions in the repository’s documentation to install all required dependencies.

3. **Run the Workflow**:  
   Execute the modules sequentially or use an automation script to run the entire pipeline:
    ```bash
    python grobid-folder.py <input-pdfs>
    python match-cit-to-bib.py
    python retrieve.py
    python match-citing-to-cited.py
    python nli-checking.py
    python consolidate.py
    ```

4. **Review the Report**:  
   After running the workflow, open the generated report to review:
   - Any mismatches between in-text citations and bibliography entries.
   - DOI issues, such as missing or invalid DOIs.
   - Discrepancies between citing sentences and the content of the cited articles.

