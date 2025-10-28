import os
import re
import json
from datetime import datetime
from pathlib import Path
import streamlit as st

from textract_client import ask_textract
from gpt_client import ask_gpt
from filter_gpt_response import filter_gpt_response


# --- Page setup ---
st.set_page_config(page_title="RB Loan Deferment IDP", layout="centered")

# PROMPT for GPT
PROMPT_TEMPLATE = """
You are an expert in multilingual document information extraction and normalization. Your assignment is to analyze OCR text that may contain both Kazakh and Russian segments.

Follow these steps precisely before producing the final JSON output:

# 1. Understand the Task
Extract the following fields:
- full_name: The person’s full name (e.g., Иванов Иван Иванович), normalized according to standard Kazakh or Russian conventions for spelling, word order, and character set — even if the OCR source is error-prone.
- doc_classification: If the document matches one of the known templates below, classify it exactly as one of these Russian strings. If none match, set it to null.
- doc_date: Main issuance date, converted to DD.MM.YYYY format.
- single_doc_type: Indicates whether exactly one distinct document type is present in the OCR text.
- single_doc_type_confidence: Confidence score from 0 to 100 for the single_doc_type decision.

## 1a. Allowed Values for doc_classification
Choose **exactly one** of the following, or `null`:
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

## 1b. Rules for Single Document Type Detection
A *document type* refers to its purpose or function, not language or formatting.
- If a document appears in multiple languages but shares the same stamp, signature, date, and number → single_doc_type = true.
- If the text contains documents with differing purposes, issuers, or organizations → single_doc_type = false.
- If uncertain → single_doc_type = false.

Confidence estimation for single_doc_type:
- 85–100: Clear single document (consistent wording, one header, one organization, single purpose).
- 50–84: Likely single, but minor duplication or noise detected.
- 0–49: Conflicting or multiple documents detected.

# 2. Extraction Rules
- If multiple dates occur, choose the principal issuance date (typically near the header or “№”).
- Ignore duplicates and minor typos.
- Never invent or infer missing data.
- If both Russian and Kazakh versions occur, produce the result in Russian.
- If several candidates for full_name are present, choose the most complete one (the longest sequence matching the Russian pattern: Фамилия Имя Отчество).

# 3. Verification
Before outputting, double-check:
- full_name: Is it complete (Фамилия Имя Отчество)?
- doc_date: Is it formatted as DD.MM.YYYY?
- doc_classification: Is it one of the allowed values or null?
- single_doc_type: Is it strictly 'true', 'false', or null (in lowercase)?
- single_doc_type_confidence: Is it a number between 0 and 100?
- Are all fields normalized and compliant with the previous guidance?

# 4. Output Format
Return strictly a single JSON object with these fields in this order (no explanations, no extra text, no markdown, no ```json formatting):
{
  "full_name": string | null,           
  "doc_classification": string | null,  
  "doc_date": string | null,            
  "single_doc_type": true | false | null,
  "single_doc_type_confidence": number
}
Do not add any text beyond this JSON object. Keep field order unchanged.

After extracting and normalizing the data, validate each field as described. If any field does not meet its requirements, review and self-correct before outputting the final JSON.

Text for analysis:
{}
"""

st.write("")
st.title("RB Loan Deferment IDP")
st.write("Загрузите один файл для распознавания (локальная обработка через Textract endpoint).")

# --- Basic paths ---
INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Simple CSS tweaks ---
st.markdown(
    """
<style>
.block-container{max-width:980px;padding-top:1.25rem;}
.meta{color:#6b7280;font-size:0.92rem;margin:0.25rem 0 1rem 0;}
.meta code{background:#f3f4f6;border:1px solid #e5e7eb;padding:2px 6px;border-radius:6px;}
.card{border:1px solid #e5e7eb;border-radius:14px;background:#ffffff;box-shadow:0 2px 8px rgba(0,0,0,.04);} 
.card.pad{padding:22px;}
.result-card{border:1px solid #e5e7eb;border-radius:14px;padding:16px;background:#fafafa;}
.stButton>button{border-radius:10px;padding:.65rem 1rem;font-weight:600;}
.stDownloadButton>button{border-radius:10px;}
</style>
""",
    unsafe_allow_html=True,
)

# --- Reason -> doc types mapping (example) ---
reasons_map = {
    "Временная нетрудоспособность заемщика по причине болезни": [
        "Лист временной нетрудоспособности (больничный лист)",
        "Выписка из стационара (выписной эпикриз)",
        "Больничный лист на сопровождающего (если предусмотрено)",
        "Заключение врачебно-консультативной комиссии (ВКК)",
        "Справка об инвалидности",
        "Справка о степени утраты общей трудоспособности",
    ],
    "Уход заемщика в декретный отпуск": [
        "Лист временной нетрудоспособности (больничный лист)",
        "Приказ о выходе в декретный отпуск по уходу за ребенком",
        "Справка о выходе в декретный отпуск по уходу за ребенком",
    ],
    "Потеря дохода заемщика (увольнение, сокращение, отпуск без содержания и т.д.)": [
        "Приказ/Справка о расторжении трудового договора",
        "Справка о регистрации в качестве безработного",
        "Приказ работодателя о предоставлении отпуска без сохранения заработной платы",
        "Справка о неполучении доходов",
        "Уведомление о регистрации в качестве лица, ищущего работу",
        "Лица, зарегистрированные в качестве безработных",
    ],
}

# --- Inputs outside form for dynamic selects ---
fio = st.text_input("ФИО", placeholder="Иванов Иван Иванович")

reason_options = ["Выберите причину"] + list(reasons_map.keys())
reason = st.selectbox(
    "Причина отсрочки",
    options=reason_options,
    index=0,
    help="Сначала выберите причину, затем подходящий тип документа",
    key="reason",
)

doc_options = ["Выберите тип документа"] + (
    reasons_map[reason] if reason in reasons_map else []
)
doc_type = st.selectbox(
    "Тип документа",
    options=doc_options,
    index=0,
    key="doc_type",
)


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\-\.\s]", "_", name.strip())
    name = re.sub(r"\s+", "_", name)
    return name or "file"


# --- Upload form ---
with st.form("upload_form", clear_on_submit=False):
    uploaded_file = st.file_uploader(
        "Выберите документ",
        type=["pdf", "jpg", "png", "jpeg"],
        accept_multiple_files=False,
        help="Поддержка: PDF, JPEG",
    )
    submitted = st.form_submit_button("Загрузить и распознать", type="primary")

if submitted:
    if not uploaded_file:
        st.warning("Пожалуйста, прикрепите файл.")
    elif reason == "Выберите причину":
        st.warning("Пожалуйста, выберите причину отсрочки.")
    elif doc_type == "Выберите тип документа":
        st.warning("Пожалуйста, выберите тип документа.")
    else:
        # Save uploaded file to input/
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _safe_filename(uploaded_file.name)
        saved_path = INPUT_DIR / f"{ts}_{base}"
        with open(saved_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.info(f"Файл сохранен: {saved_path}")

        # Run Textract pipeline
        try:
            pages_path = ask_textract(str(saved_path), output_dir=str(OUTPUT_DIR), save_json=True, save_text=True)
            st.success("Распознавание завершено.")

            # Load pages JSON
            with open(pages_path, "r", encoding="utf-8") as f:
                pages_obj = json.load(f)
            pages = pages_obj.get("pages", []) if isinstance(pages_obj, dict) else []

            # Download button
            with open(pages_path, "rb") as f:
                st.download_button(
                    label="Скачать JSON со страницами",
                    data=f.read(),
                    file_name=os.path.basename(pages_path),
                    mime="application/json",
                )

            # Simple per-page preview
            if pages:
                page_numbers = [p.get("page_number") for p in pages]
                default_index = 0
                selected = st.selectbox("Страница", options=list(range(len(pages))), format_func=lambda i: f"Стр. {page_numbers[i] if page_numbers[i] is not None else i+1}", index=default_index)
                st.text_area("Текст страницы", value=pages[selected].get("text", ""), height=400)
                pages_json_str = json.dumps(pages_obj, ensure_ascii=False)
                if pages_json_str:
                    prompt = PROMPT_TEMPLATE.replace("{}", pages_json_str, 1)
                    try:
                        gpt_raw = ask_gpt(prompt)
                        # Save raw GPT response
                        try:
                            with open(OUTPUT_DIR / "gpt_response_raw.json", "w", encoding="utf-8") as gf:
                                gf.write(gpt_raw)
                        except Exception:
                            pass
                        # Filter and show/download the extracted fields
                        try:
                            filtered_path = filter_gpt_response(str(OUTPUT_DIR / "gpt_response_raw.json"), str(OUTPUT_DIR))
                            with open(filtered_path, "r", encoding="utf-8") as ff:
                                filtered_obj = json.load(ff)
                            st.json(filtered_obj)
                            with open(filtered_path, "rb") as ff:
                                st.download_button(
                                    label="Скачать JSON (фильтрованный результат)",
                                    data=ff.read(),
                                    file_name=os.path.basename(filtered_path),
                                    mime="application/json",
                                )
                        except Exception:
                            # Fallback: show raw as JSON if possible, else code
                            try:
                                gpt_json = json.loads(gpt_raw)
                                st.json(gpt_json)
                            except Exception:
                                st.code(gpt_raw, language="json")
                    except Exception as e:
                        st.error(f"Ошибка GPT: {e}")
            else:
                st.info("Нет распознанных страниц в результате.")
        except Exception as e:
            st.error(f"Ошибка распознавания: {e}")
            st.exception(e)