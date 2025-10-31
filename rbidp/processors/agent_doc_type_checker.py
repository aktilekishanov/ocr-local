from rbidp.clients.gpt_client import ask_gpt
import json

PROMPT = """
SYSTEM INSTRUCTION:
You are a precise document-type classifier. Your goal is to decide if the input OCR text represents ONE distinct document type or multiple.

TASK:
Return strictly a JSON object:
{"single_doc_type": boolean}

DEFINITIONS:
- A *document type* = the document’s purpose (e.g., order, certificate, medical form, ID, decree).  
- Different languages, duplicated headers, or OCR artifacts do NOT mean multiple documents.  
- Only count as multiple if content clearly shows distinct purposes, issuers, people, or form numbers.

DECISION RULES:
1. Same form number, same organization, same person, same purpose → true.  
2. Repeated headers, bilingual duplicates, or OCR noise → ignore → still true.  
3. Two or more unrelated forms (different document names, people, or cases) → false.  
4. If unclear, but all content aligns with one document → default to true.

EXAMPLES:
- “БҰЙРЫҚ / ПРИКАЗ” bilingual with same signature → true  
- “ПРИКАЗ” + “СПРАВКА” → false  
- Header repeated due to OCR → true  
- Two different signatures for two people → false

OUTPUT:
Respond with only:
{"single_doc_type": true}
or
{"single_doc_type": false}

INPUT TEXT:
{}
"""

def check_single_doc_type(pages_obj: dict) -> str:
    pages_json_str = json.dumps(pages_obj, ensure_ascii=False)
    if not pages_json_str:
        return ""
    prompt = PROMPT.replace("{}", pages_json_str, 1)
    return ask_gpt(prompt)
