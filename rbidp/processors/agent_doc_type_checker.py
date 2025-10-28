from rbidp.clients.gpt_client import ask_gpt
import json

PROMPT = """
### Objective
Determine whether the input image contains **exactly one distinct document type**.


### Definition
A *document type* refers to the function or purpose of the document (e.g., employment certificate, order/decree, medical leave notice, national ID, power of attorney) — **not** its language or layout variation.


### Guidelines
1. If a single document appears in multiple languages (e.g., Kazakh and Russian) but shares the same stamp, signature, date, document number, and structure → "single_doc_type": true.
2. If the page contains documents with different purposes, issuers, or organizations → "single_doc_type": false.
3. If the distinction is unclear → "single_doc_type": false.

### Example Decision Rules
- “БҰЙРЫҚ / ПРИКАЗ” (Kazakh + Russian, same stamp/signature) → "single_doc_type": true 
- “ПРИКАЗ” (Order) + “Справка” (Certificate) → "single_doc_type": false 
- Faint or partial duplicate of same document → "single_doc_type": false 


### Output
Return strictly the following JSON object (no explanations, no extra text, no Markdown formatting, and no ```json formatting):
{
  "single_doc_type": boolean
}


Text for analysis:
{}
"""

def check_single_doc_type(pages_obj: dict) -> str:
    pages_json_str = json.dumps(pages_obj, ensure_ascii=False)
    if not pages_json_str:
        return ""
    prompt = PROMPT.replace("{}", pages_json_str, 1)
    return ask_gpt(prompt)
