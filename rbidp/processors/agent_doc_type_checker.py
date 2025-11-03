from rbidp.clients.gpt_client import ask_gpt
import json

# PROMPT = """
# SYSTEM INSTRUCTION:
# You are a precise document-type classifier. Your goal is to decide if the input OCR text represents ONE distinct document type or multiple.

# TASK:
# Return strictly a JSON object:
# {"single_doc_type": boolean}

# DEFINITIONS:
# - A *document type* = the document’s purpose (e.g., order, certificate, medical form, ID, decree).  
# - Different languages, duplicated headers, or OCR artifacts do NOT mean multiple documents.  
# - Only count as multiple if content clearly shows distinct purposes, issuers, people, or form numbers.

# DECISION RULES:
# 1. Same form number, same organization, same person, same purpose → true.  
# 2. Repeated headers, bilingual duplicates, or OCR noise → ignore → still true.  
# 3. Two or more unrelated forms (different document names, people, or cases) → false.  
# 4. If unclear, but all content aligns with one document → default to true.

# EXAMPLES:
# - “БҰЙРЫҚ / ПРИКАЗ” bilingual with same signature → true  
# - “ПРИКАЗ” + “СПРАВКА” → false  
# - Header repeated due to OCR → true  
# - Two different signatures for two people → false

# OUTPUT:
# Respond with only:
# {"single_doc_type": true}
# or
# {"single_doc_type": false}

# INPUT TEXT:
# {}
# """

PROMPT = """
You are an **ultra-precise OCR document-type classifier**.

Your task: Decide if the provided OCR text represents **one single document type** or **multiple distinct document types**.

Return **strictly** one JSON object:
{"single_doc_type": true}
or
{"single_doc_type": false}

### PRIMARY OBJECTIVE
Focus on the *purpose* and *issuer* of the document — not formatting, duplication, or noise.
You must be conservative: only output `false` if there is **clear and explicit** evidence that more than one separate document exists.

---

### RULE HIERARCHY (most important first)
1. **Default to true.** If it’s not obvious that multiple documents exist, output `true`.
2. **Ignore all OCR noise**, random English words, partial lines, numbers, or page fragments. These are NOT indicators of a second document.
3. **Ignore repetition** of headers, bilingual text (Kazakh/Russian), stamps, or partial duplicates — they belong to the same document.
4. **Output false only if** you detect at least one of the following:
   - Two or more different document names (e.g., “ПРИКАЗ” and “СПРАВКА”).
   - Two distinct issuers or organizations (e.g., different ministries or companies).
   - Two unrelated people or identifiers (e.g., two different names or form numbers with unrelated context).
   - Two clearly separate document purposes (e.g., employment order vs. medical certificate).
5. **Do not overfit to surface noise.** Assume OCR outputs are messy and incomplete — reason at the semantic level.

---

### HEURISTICS & TESTS
- All fragments could plausibly belong to one form → true.
- If you are uncertain but there’s no explicit contradiction → true.
- Random English tokens like “STATE”, “REPAIR”, “AMERICAN” → ignore → still true.
- A page break or repeated number → ignore → still true.
- Only when the text clearly shows multiple *independent* documents → false.

---

### EXAMPLES
true:
- “БҰЙРЫҚ / ПРИКАЗ” bilingual duplicate of one order.
- Medical form with OCR garbage like “AMERICAN”, “STATE”, “Repair”.
- Repeated header due to scanning errors.

false:
- “ПРИКАЗ” followed by “СПРАВКА” (two unrelated forms).
- Two separate letters, each signed by a different person.
- One page refers to an employment order, another to a marriage certificate.

---

### OUTPUT REQUIREMENTS
- Respond **only** with:
  {"single_doc_type": true}
  or
  {"single_doc_type": false}
- No explanations, no text before or after, no additional symbols.

---

OCR INPUT:
{}
"""


def check_single_doc_type(pages_obj: dict) -> str:
    pages_json_str = json.dumps(pages_obj, ensure_ascii=False)
    if not pages_json_str:
        return ""
    prompt = PROMPT.replace("{}", pages_json_str, 1)
    return ask_gpt(prompt)
