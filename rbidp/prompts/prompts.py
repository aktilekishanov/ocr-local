#image input prompt from aws

prompt = """
## Role and Objective
You are an expert in document structure and classification. Your task is to analyze an input image or PDF page and produce a structured JSON output according to the instructions below.

You may internally reason through your steps, but your final output must consist of a **single JSON object** that conforms exactly to the specified schema.

---

## Part 1 — Document Type Classification

### Objective
Determine whether the input image contains **exactly one distinct document type**.

### Definition
A *document type* refers to the function or purpose of the document (e.g., employment certificate, order/decree, medical leave notice, national ID, power of attorney) — **not** its language or layout variation.

### Guidelines
1. If a single document appears in multiple languages (e.g., Kazakh and Russian) but shares the same stamp, signature, date, document number, and structure → `"single_doc_type": true`.
2. If the page contains documents with different purposes, issuers, or organizations → `"single_doc_type": false`.
3. If the distinction is unclear → `"single_doc_type": false`.

### Example Decision Rules
- “БҰЙРЫҚ / ПРИКАЗ” (Kazakh + Russian, same stamp/signature) → `"single_doc_type": true`
- “ПРИКАЗ” (Order) + “Справка” (Certificate) → `"single_doc_type": false`
- Faint or partial duplicate of same document → `"single_doc_type": false`

---

## Part 2 — Stamp and QR Code Detection

Determine whether the scanned document contains:
1. A **stamp** (round or rectangular).
2. A **QR code** (square matrix barcode).

For each, output:
- `*_present`: `true` or `false`
- `*_confidence`: 0–100 indicating detection confidence

---

## Output Format
Return **only** a single valid JSON object strictly matching this schema.  
Do **not** include explanations, notes, or any text outside the JSON block.

{
  "single_doc_type": true | false,
  "single_doc_type_confidence": 0-100,
  "stamp_present": true | false,
  "stamp_confidence": 0-100,
  "qr_present": true | false,
  "qr_confidence": 0-100
}

INPUT IMAGE FOR ANALYSIS:
{image}
"""










# old prompt from app.py

PROMPT_TEMPLATE = """
You are an expert in multilingual document information extraction and normalization.
Your task is to analyze a noisy OCR text that may contain both Kazakh and Russian fragments.


Follow these steps precisely before producing the final JSON:


STEP 1 — UNDERSTAND THE TASK
You must extract the following information:
- full_name: full name of the person (e.g. **Иванов Иван Иванович**)
- doc_classification: if document matches one of the known templates, classify it as one of:
  - "Лист временной нетрудоспособности (больничный лист)"
  - "Приказ о выходе в декретный отпуск по уходу за ребенком"
  - "Справка о выходе в декретный отпуск по уходу за ребенком"
  - "Выписка из стационара (выписной эпикриз)"
  - "Больничный лист на сопровождающего (если предусмотрено)"
  - "Заключение врачебно-консультативной комиссии (ВКК)"
  - "Справка об инвалидности"
  - "Справка о степени утраты общей трудоспособности"
  - "Приказ/Справка о расторжении трудового договора"
  - "Справка о регистрации в качестве безработного"
  - "Приказ работодателя о предоставлении отпуска без сохранения заработной платы"
  - "Справка о неполучении доходов"
  - "Уведомление о регистрации в качестве лица, ищущего работу"
  - "Лица, зарегистрированные в качестве безработных"
  - null
- doc_date: main issuance date (convert to format DD.MM.YYYY)


STEP 2 — EXTRACTION RULES
- If several dates exist, choose the main issuance date (usually near header or "№").
- Ignore duplicates or minor typos.
- When the value is missing, set it strictly to `null`.
- Do not invent or assume missing data.
- If both Russian and Kazakh versions exist, output result in Russian.


STEP 3 — THINK BEFORE ANSWERING
Double-check:
- Is full_name complete (Фамилия Имя Отчество)?
- Is doc_date formatted as DD.MM.YYYY?
- Are there exactly 3 keys in the final JSON?
- Is doc_classification one of the allowed options or null?


STEP 4 — OUTPUT STRICTLY IN THIS JSON FORMAT (no explanations, no extra text, no Markdown formatting, and no ```json formatting)
{
  "full_name": string | null,
  "doc_classification": string | null,
  "doc_date": string | null,
}


Text for analysis:
{}
"""