#!/usr/bin/env python3
import logging
import re
import requests
import torch
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
    "cointegrated/rubert-base-cased-nli-threeway": ("cointegrated/rubert-base-cased-nli-threeway", 512),
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

def nli_candidates_all_results(model_name, citing_sentence, cited_xml):
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
    for window_len in [1, 2, 3]:
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
            entailments = [p for p in preds if "entail" in p["label"].lower()]
            score = max([p["score"] for p in entailments], default=0.0)
            if score > 0.0:
                all_results.append((window_text, score))
    return sorted(all_results, key=lambda x: x[1], reverse=True)

def nli_candidates_top5_results(model_name, citing_sentence, cited_xml, window_types=[1, 2, 3]):
    all_results = nli_candidates_all_results(model_name, citing_sentence, cited_xml)
    return all_results[:5]

def citation_checker(citing_sentence, tei_xml, citation_id, model_name, window_options):
    """
    Processes the TEI XML of the cited article and uses the selected NLI model and window options
    to generate a list of candidate contextual windows. The function returns the extracted context
    (the raw <body> of the TEI) and updates the candidate radio component with the top 5 candidates.
    """
    soup = BeautifulSoup(tei_xml, "xml")
    body = soup.find("body")
    if not body:
        return "Error: <body> not found", gr.update(choices=[], value=None)
    extracted_context = str(body)
    w_map = {"1 Sentence": 1, "2 Sentences": 2, "3 Sentences": 3}
    w_types = [w_map[o] for o in window_options]
    top5 = nli_candidates_top5_results(model_name, citing_sentence, str(body), w_types)
    if not top5:
        return extracted_context, gr.update(choices=[], value=None)
    radio_list = []
    for i, (ctx, sc) in enumerate(top5, 1):
        label = f"Candidate {i}:\n{ctx}\n(Confidence: {sc:.4f})"
        radio_list.append(label)
    return extracted_context, gr.update(choices=radio_list, value=None)

# -----------------------
# Gradio Interface: NLI Checking
# -----------------------
with gr.Blocks(css=".gradio-container { font-family: sans-serif; }") as demo:
    gr.Markdown("## NLI Checking")
    gr.Markdown("Enter a citing sentence, a citation ID (for reference), and the TEI XML of a cited article. Then, select an NLI model and window types to generate candidate contextual windows. Choose the best candidate from the provided options.")

    citing_sentence_input = gr.Textbox(label="Citing Sentence")
    citation_id_input = gr.Textbox(label="Citation ID")
    tei_xml_input = gr.Textbox(label="Cited TEI XML", lines=8)
    
    model_dropdown = gr.Dropdown(
        label="Select NLI Model",
        choices=list(NLI_MODELS_DEFAULT.keys()),
        value="BlackBeanie DeBERTa-V3-Large"
    )
    window_checkbox = gr.CheckboxGroup(
        label="Window Types",
        choices=["1 Sentence", "2 Sentences", "3 Sentences"],
        value=["1 Sentence", "2 Sentences", "3 Sentences"]
    )
    
    run_button = gr.Button("Run Citation Check")
    extracted_context_box = gr.Textbox(label="Extracted Context", lines=5)
    candidate_radio = gr.Radio(label="Select Correct Candidate", choices=[], type="value", interactive=True)
    
    run_button.click(
        fn=citation_checker,
        inputs=[citing_sentence_input, tei_xml_input, citation_id_input, model_dropdown, window_checkbox],
        outputs=[extracted_context_box, candidate_radio]
    )
    
demo.launch(share=True)