#!/usr/bin/env python3
import logging
import re
import requests
import torch
import json
import os
import uuid
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
from bs4 import BeautifulSoup
import gradio as gr

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# -----------------------
# Configuration
# -----------------------
NLI_MODELS_DEFAULT = {
    "BlackBeanie DeBERTa-V3-Large": ("BlackBeenie/nli-deberta-v3-large", 512),
    "cross-encoder/nli-deberta-v3-base": ("cross-encoder/nli-deberta-v3-base", 1024),
    "sileod/deberta-v3-base-tasksource-nli": ("sileod/deberta-v3-base-tasksource-nli", 512),
    "amoux/scibert_nli_squad": ("amoux/scibert_nli_squad", 512)
}

# -----------------------
# Helper Functions
# -----------------------
def normalize_text(text):
    text = re.sub(r'\.\s*\.\s*\.', '...', text)
    text = text.replace('…', '...')
    return re.sub(r'\s+', ' ', text).strip()

def load_nli_model_results(model_name):
    if model_name in NLI_MODELS_DEFAULT:
        model_path, max_tokens = NLI_MODELS_DEFAULT[model_name]
    else:
        model_path, max_tokens = model_name, 512
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model.to(device)
    nli_pipeline = pipeline("text-classification", model=model, tokenizer=tokenizer, device=device)
    return nli_pipeline, tokenizer, max_tokens

def nli_candidates_all_results(model_name, citing_sentence, cited_xml, window_types=[1, 2, 3]):
    soup = BeautifulSoup(cited_xml, "xml")
    # Remove <ref> tags to get clean text
    for ref in soup.find_all("ref"):
        ref.decompose()
    sentences = [
        s.get_text(" ", strip=True)
        for s in soup.find_all(lambda tag: tag.name == "s" or tag.name.endswith(":s"))
        if len(s.get_text(" ", strip=True).split()) >= 3
    ]
    if not sentences:
        sentences = [sent for sent in re.split(r'(?<=[.!?])\s+', cited_xml.strip()) if len(sent.split()) >= 3]
    nli_pipeline, tokenizer, max_tokens = load_nli_model_results(model_name)
    all_results = []
    for window_len in window_types:
        for i in range(len(sentences) - window_len + 1):
            window = sentences[i:i+window_len]
            if any(len(w.split()) < 3 for w in window):
                continue
            window_text = " ".join(window)
            norm_window = normalize_text(window_text)
            input_text = f"{citing_sentence} [SEP] {norm_window}"
            try:
                preds = nli_pipeline(input_text, truncation=True, max_length=max_tokens)
            except Exception as e:
                logging.error(f"Error running NLI pipeline: {e}")
                continue
            # Process entailment predictions
            entailments = [p for p in preds if "entail" in p["label"].lower()]
            if entailments:
                score = max(p["score"] for p in entailments)
                if score > 0.0:
                    all_results.append((window_text, score, "Entailing"))
            # Process contradiction predictions
            contradictions = [p for p in preds if "contradict" in p["label"].lower()]
            if contradictions:
                score = max(p["score"] for p in contradictions)
                if score > 0.0:
                    all_results.append((window_text, score, "Contradicting"))
    return sorted(all_results, key=lambda x: x[1], reverse=True)

def nli_candidates_top5_results(model_name, citing_sentence, cited_xml, window_types=[1, 2, 3]):
    all_results = nli_candidates_all_results(model_name, citing_sentence, cited_xml, window_types)
    return all_results[:5]


def write_log_if_enabled(log_data, logging_toggle, log_filename):
    """
    Writes the given log_data as JSON to a log file if logging is enabled and a filename is provided.
    """
    global PROJECT_HOME
    if logging_toggle == "On" and log_filename.strip():
        # Ensure .json extension
        if not log_filename.strip().endswith(".json"):
            log_filename = log_filename.strip() + ".json"
        log_dir = os.path.join(PROJECT_HOME, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        filepath = os.path.join(log_dir, log_filename)

        # Read any existing JSON array
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                try:
                    existing_logs = json.load(f)
                except json.JSONDecodeError:
                    existing_logs = []
        else:
            existing_logs = []

        # Append the new log entry
        existing_logs.append(log_data)

        # Overwrite the file with the updated array
        with open(filepath, "w") as f:
            json.dump(existing_logs, f, indent=2)


def citation_checker(raw_citing_sentence, citing_sentence, tei_xml, model_name, window_options, candidate_type_options, logging_toggle, log_filename):
    """
    Checks the citation by extracting the <body> from the TEI XML,
    generates candidate contexts using a moving window, and logs the results
    if logging is enabled.

    Returns:
      - extracted_context: The string representation of the <body> element.
      - A Gradio update for the candidate checkbox options.
    """
    soup = BeautifulSoup(tei_xml, "xml")
    body = soup.find("body")
    if not body:
        log_data = {
            "uid": str(uuid.uuid4()),
            "error": "<body> not found",
            "raw_citing_sentence": raw_citing_sentence
        }
        write_log_if_enabled(log_data, logging_toggle, log_filename)
        return "Error: <body> not found", gr.update(choices=[], value=None)
    
    extracted_context = str(body)
    w_map = {"1 Sentence": 1, "2 Sentences": 2, "3 Sentences": 3}
    w_types = [w_map[o] for o in window_options]
    all_candidates = nli_candidates_all_results(model_name, citing_sentence, str(body), w_types)
    filtered = []
    if "Entailing candidates" in candidate_type_options:
         filtered += [cand for cand in all_candidates if cand[2] == "Entailing"]
    if "Contradicting candidates" in candidate_type_options:
         filtered += [cand for cand in all_candidates if cand[2] == "Contradicting"]
    filtered = sorted(filtered, key=lambda x: x[1], reverse=True)
    top_candidates = filtered[:5]
    
    # Build candidate labels and detailed candidate info
    candidate_labels = []
    candidate_details = []
    entailing_count = 1
    contradicting_count = 1
    for (ctx, sc, cand_type) in top_candidates:
         if cand_type == "Entailing":
             label = f"Entailing {entailing_count}: {ctx}\n(Confidence: {sc:.4f})"
             entailing_count += 1
         elif cand_type == "Contradicting":
             label = f"Contradicting {contradicting_count}: {ctx}\n(Confidence: {sc:.4f})"
             contradicting_count += 1
         candidate_labels.append(label)
         candidate_details.append({
             "candidate_text": ctx,
             "candidate_type": cand_type,
             "confidence": sc,
             "selected": False
         })
    
    # Get NLI pipeline configuration details
    if model_name in NLI_MODELS_DEFAULT:
        model_path, max_tokens = NLI_MODELS_DEFAULT[model_name]
    else:
        model_path, max_tokens = model_name, 512

    # Build the detailed log data
    log_data = {
         "uid": str(uuid.uuid4()),
         "raw_citing_sentence": raw_citing_sentence,
         "extracted_context": extracted_context,
         "model_used": model_name,
         "nli_pipeline_config": {
             "model_path": model_path,
             "max_tokens": max_tokens
         },
         "moving_window_options": window_options,
         "used_window_sizes": w_types,
         "candidate_details": candidate_details
    }
    write_log_if_enabled(log_data, logging_toggle, log_filename)
    return extracted_context, gr.update(choices=candidate_labels, value=[]), candidate_details
    

def add_case(citing_sentence, tei_xml, model_name, window_options, correct_candidate, cases):
    soup = BeautifulSoup(tei_xml, "xml")
    body = soup.find("body")
    extracted_context = str(body) if body else "No <body> found"
    new_case = {
        "citing_sentence": citing_sentence,
        "tei_xml": tei_xml,
        "model_used": model_name,
        "window_options": window_options,
        "correct_candidate": correct_candidate,
        "extracted_context": extracted_context
    }
    cases.append(new_case)
    return cases, f"Case added. Total cases: {len(cases)}."

def find_rank_conf(case, model_name):
    selected_candidates = case["correct_candidate"]
    
    # If no candidates selected, return a warning
    if not selected_candidates:
        return "<span style='color: red;'>No candidates selected</span>"
    
    # nli_candidates_all_results for the entire case
    all_ = nli_candidates_all_results(model_name, case["citing_sentence"], case["extracted_context"])
    
    # We'll collect the results for each selected candidate
    result_snippets = []
    
    # Make sure we handle both list and string
    if isinstance(selected_candidates, str):
        selected_candidates = [selected_candidates]
    
    # Process each candidate
    for candidate_str in selected_candidates:
        # Split lines. Typically, first line has the text (like "Entailing 1: ..."),
        # second line has confidence. We'll parse the first line to extract text after colon.
        lines = candidate_str.splitlines()
        if len(lines) >= 1:
            first_line = lines[0]
            # e.g., "Entailing 1: grading can be harmful..."
            parts = first_line.split(":", 1)
            text_only = parts[1].strip() if len(parts) > 1 else first_line.strip()
        else:
            text_only = candidate_str.strip()

        # Now we match text_only with the results from all_
        found_match = False
        for idx, (ctx, score, cand_type) in enumerate(all_, 1):
            if ctx.strip() == text_only:
                style = "color: green;" if cand_type == "Entailing" else "color: red;"
                snippet = f"<span style='{style}'>{cand_type} {idx} (Conf: {score:.4f})</span>"
                result_snippets.append(snippet)
                found_match = True
                break  # Stop once we find the first match

        if not found_match:
            result_snippets.append("<span style='color: red;'>No matching candidate found</span>")
    
    # Combine all results into a single cell, each snippet separated by <br>
    return "<br>".join(result_snippets)

def log_entailment_decisions(selected_candidates, candidate_details, raw_citing_sentence, citing_sentence, model_name, window_options, candidate_type_options, logging_toggle, log_filename):
    """
    Processes the candidate selections and writes a final log entry.
    For each candidate in candidate_details, if its candidate_text appears in any selected candidate label,
    it is marked as selected; otherwise, it is marked as 'Neutral'.
    A single log entry is then written that includes all the relevant input details.
    """
    import datetime
    # Update candidate details based on selected candidates.
    for cand in candidate_details:
        is_selected = any(cand["candidate_text"] in sel for sel in selected_candidates)
        if is_selected:
            cand["selected"] = True
        else:
            cand["selected"] = False
            cand["candidate_type"] = "Neutral"

    final_log_entry = {
         "uid": str(uuid.uuid4()),
         "raw_citing_sentence": raw_citing_sentence,
         "corrected_citing_sentence": citing_sentence,
         "model_used": model_name,
         "window_options": window_options,
         "candidate_type_options": candidate_type_options,
         "final_candidate_selections": candidate_details,
         "timestamp": str(datetime.datetime.now())
    }
    write_log_if_enabled(final_log_entry, logging_toggle, log_filename)
    return "Final candidate decisions logged.", candidate_details

def run_comparison(custom_links, cases):
    lines = [l.strip() for l in custom_links.splitlines() if l.strip()]
    all_models = dict(NLI_MODELS_DEFAULT)
    for link in lines:
        if link not in all_models:
            all_models[link] = (link, 512)
    col_headers = [f"Case {i+1}" for i, c in enumerate(cases)]
    html = ["<table border='1' style='border-collapse: collapse;'>"]
    html.append("<tr><th>Model</th>")
    for col in col_headers:
        html.append(f"<th>{col}</th>")
    html.append("</tr>")
    for model in all_models:
        html.append(f"<tr><td>{model}</td>")
        for c in cases:
            rank_html = find_rank_conf(c, model)
            html.append(f"<td style='padding:5px;'>{rank_html}</td>")
        html.append("</tr>")
    html.append("</table>")
    return "\n".join(html)

# -----------------------
# Gradio Interface: NLI Checking
# -----------------------
with gr.Blocks(css=".gradio-container { font-family: sans-serif; }") as demo:
    gr.Markdown(
        "Enter a citing sentence, citation ID, and the TEI XML of a cited article.\n"
        "Select an NLI model and window types, then choose the best candidate.\n"
        "These fields can also be updated from the Selection tab."
    )
    # New raw citing sentence input
    raw_citing_sentence_input = gr.Textbox(label="Paste full raw citing sentence here", lines=3)
    
    citing_sentence_input = gr.Textbox(label="Place extracted and corrected relevant portion of the citing sentence here")
    tei_xml_input = gr.Textbox(label="Paste full text of the cited resource TEI file here", lines=8)
    # Remove log textbox and add logging toggle radio button along with log filename input
    logging_toggle = gr.Radio(label="Logging", choices=["On", "Off"], value="Off", type="value")
    log_filename_input = gr.Textbox(label="Log File Name (in /logs)", lines=1, placeholder="Enter log file name")
    
    model_dropdown = gr.Dropdown(
        label="Select which NLI Model you wish to use",
        choices=list(NLI_MODELS_DEFAULT.keys()),
        value="BlackBeanie DeBERTa-V3-Large"
    )
    window_checkbox = gr.CheckboxGroup(
        label="Select number of sentences in the moving window",
        choices=["1 Sentence", "2 Sentences", "3 Sentences"],
        value=["1 Sentence", "2 Sentences", "3 Sentences"]
    )
    candidate_type_checkbox = gr.CheckboxGroup(
    label="Select candidate types to report",
    choices=["Entailing candidates", "Contradicting candidates"],
    value=["Entailing candidates", "Contradicting candidates"]
    )
    
    run_button = gr.Button("Run Citation Check")
    extracted_context_box = gr.Textbox(label="Relevant portion extracted from the cited record", lines=5)
    candidate_checkbox = gr.CheckboxGroup(label="Select Correct Candidates", choices=[], interactive=True)
    candidate_details_state = gr.State([])
    cases_state = gr.State([])
    run_button.click(
        fn=citation_checker,
        inputs=[raw_citing_sentence_input, citing_sentence_input, tei_xml_input, model_dropdown, window_checkbox, candidate_type_checkbox, logging_toggle, log_filename_input],
        outputs=[extracted_context_box, candidate_checkbox, candidate_details_state]
    )
    
    log_choices_button = gr.Button("Log Choices")
    final_status = gr.Textbox(label="Final Decision Log Status", lines=2)
    # Use candidate_checkbox selections and the hidden candidate_details_state
    log_choices_button.click(
        fn=log_entailment_decisions,
        inputs=[
            candidate_checkbox,
            candidate_details_state,
            raw_citing_sentence_input,
            citing_sentence_input,
            model_dropdown,
            window_checkbox,
            candidate_type_checkbox,
            logging_toggle,
            log_filename_input
        ],
        outputs=[final_status, candidate_details_state]
    )

    gr.Markdown("Add this result as a benchmark case for later comparison:")
    add_case_button = gr.Button("Add Case")
    case_status = gr.Textbox(label="Case Status", lines=2)
    add_case_button.click(
        fn=add_case,
        inputs=[citing_sentence_input, tei_xml_input, model_dropdown, window_checkbox, candidate_checkbox, cases_state],
        outputs=[cases_state, case_status]
    )
    
    gr.Markdown("Run comparison across all stored cases:")
    custom_model_links = gr.Textbox(label="Paste HuggingFace links to additional models here", lines=4)
    compare_button = gr.Button("Compare")
    compare_html = gr.HTML(label="Comparison Table")
    compare_button.click(
        fn=run_comparison,
        inputs=[custom_model_links, cases_state],
        outputs=compare_html
    )
    
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NLI Checking Script")
    parser.add_argument("-f", "--home", help="Project home directory", default=".")
    args = parser.parse_args()
    PROJECT_HOME = args.home  # override the default PROJECT_HOME
    demo.launch(share=True)

"""

⸻

NLI Citation Checking Script Documentation

Overview

This script provides an interactive Gradio-based interface for performing Natural Language Inference (NLI)–based citation checking. It is designed with two primary use cases in mind:
	1.	Citation Verification Workflow:
Work through multiple citing sentences by extracting the relevant content from cited resources and recording entailment decisions in a json log (which may be useful for fine tuning/training NLI models and/or reconstructing entailment links within library held resources.
	2.	Model Comparison and Selection:
Evaluate different NLI models to determine which one produces the best candidate sets for your citation checking needs. 

⸻

Use Case 1: Citation Verification Workflow

Purpose
	•	Verify and refine citations:
The tool extracts the <body> of a full TEI XML document and generates multiple candidate options using a moving window approach.
	•	Select and log entailment decisions:
Users review candidate options (each with a confidence score) and select the ones (plural) that support the citing sentence. Once the user is satisfied with their selections, they log their decisions. Unselected candidates are recorded as “Neutral” to maintain balanced training data.

Workflow
	1.	Input Citation Details:
	•	Raw Citing Sentence: Paste the full raw citing sentence from the TEI source.
	•	Corrected Citing Sentence: Enter the extracted and refined portion of the citing sentence.
	•	TEI XML: Paste the complete TEI XML content of the cited resource.
	2.	Select NLI Model & Settings:
	•	Model Selection: Choose from a predefined list of NLI models.
	•	Window Options: Select one or more moving window sizes (e.g., “1 Sentence”, “2 Sentences”, “3 Sentences”).
	•	Candidate Types: Specify whether to generate “Entailing” and/or “Contradicting” candidate windows.
	3.	Run Citation Check:
Click the “Run Citation Check” button to extract the relevant <body> content and generate candidate entailing windows. The top five candidates (with confidence scores) will be displayed as options.
	4.	Select Correct Candidates:
Review the candidate list and check the boxes corresponding to the candidate windows that support the citing sentence.
	5.	Log Final Decisions:
Once satisfied with the selections, click the “Log Choices” button. This logs a final JSON record that includes:
	•	Raw and corrected citing sentences.
	•	Model used, window settings, and candidate type options.
	•	Detailed candidate information (candidate text, entailment/contradiction, confidence, and whether the candidate was selected or marked as neutral).
	•	A unique identifier and timestamp.
	6.	Case Benchmarking (Optional):
Use the “Add Case” feature to store a citation case for later comparison or further analysis.

⸻

Use Case 2: Model Comparison and Selection

Purpose
	•	Evaluate multiple NLI models:
When unsure which NLI model best fits your citation verification process, the script enables you to run comparisons across models.
	•	Determine performance metrics:
Compare how each model ranks candidate windows for a given citation case to identify which model generates the most reliable and interpretable entailment decisions.

Workflow
	1.	Prepare a Set of Benchmark Cases:
Use the “Add Case” functionality to store a set of citation cases. Each case includes the citing sentence, extracted context, and candidate decisions.
	2.	Specify Additional Models (Optional):
You can supply additional Hugging Face model links via a textbox to include in the comparison, expanding beyond the default models.
	3.	Run Comparison:
Click the “Compare” button. The script will generate an HTML table comparing all stored cases across the selected models. Each cell shows the model’s ranking of the candidate windows (including their entailment type and confidence scores).
	4.	Interpret Results:
The resulting table allows you to see which models consistently select the candidates that best align with the citing sentence, helping you decide on the most effective model for your needs.

⸻

Technical Details

Core Functions
	•	citation_checker(...)
Extracts the <body> from the TEI XML, generates candidate contextual windows, and logs preliminary details (including candidate details) in a hidden state.
	•	nli_candidates_all_results(...) & nli_candidates_top5_results(...)
Generate candidate windows using the moving window approach and filter/sort them based on NLI model confidence scores.
	•	log_entailment_decisions(...)
Processes the final candidate selections (marking unselected ones as “Neutral”) and writes a complete JSON log entry when the user clicks “Log Choices.”
	•	add_case(...)
Adds the current citation case to the cases state for later model comparison.
	•	run_comparison(...)
Compares stored cases across multiple NLI models and generates an HTML table summarizing candidate rankings.

Logging
	•	JSON Logging:
Log entries are written as valid JSON arrays (with a .json extension) to a specified directory (via the -f flag). Each log record contains all details needed for fine-tuning or auditing NLI decisions.
	•	Granular Details:
Each log entry includes the raw and corrected citing sentences, model configuration details, window options, candidate details, a unique ID, and a timestamp.

⸻

Running the Script

Prerequisites
	•	Python 3.x
	•	Required libraries: gradio, transformers, torch, beautifulsoup4, requests, etc.
	•	Internet connection (to download model weights and interact with Hugging Face APIs)

Command-Line usage
	•	python nli-checking.py -f /path/to/project/home
	•	The -f flag specifies the project home directory, which is used to store log files (under a /logs subdirectory).
Interface Overview
	•	Inputs:
	•	Raw citing sentence
	•	Corrected citing sentence
	•	TEI XML content
	•	NLI model selection
	•	Moving window and candidate type options
	•	Outputs:
	•	Extracted context display
	•	Candidate list for selection
	•	Hidden state for candidate details
	•	Final log status
	•	Buttons:
	•	“Run Citation Check”
	•	“Log Choices”
	•	“Add Case”
	•	“Compare” (for model evaluation)

⸻

Conclusion

This script serves dual purposes: it enables detailed citation verification with robust logging of entailment decisions and facilitates the comparison of multiple NLI models. By following the outlined workflows, users can both refine individual citations and select the best model for their domain-specific citation checking needs.

For further assistance or to suggest improvements, please refer to the inline comments or contact the developer.

"""