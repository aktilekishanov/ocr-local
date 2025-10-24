import os
import re
from datetime import datetime
from pathlib import Path
import streamlit as st

from textract_client import ask_textract


# --- Page setup ---
st.set_page_config(page_title="RB Loan Deferment IDP", layout="centered")

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
        "Заключение врачебно-консультативной комиссии (ВКК).",
        "Справка об инвалидности.",
        "Справка о степени утраты общей трудоспособности.",
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
            text = ask_textract(str(saved_path), output_dir=str(OUTPUT_DIR), save_json=True, save_text=True)
            st.success("Распознавание завершено.")

            with st.expander("Показать распознанный текст", expanded=True):
                st.text_area("Результат", value=text, height=400)
        except Exception as e:
            st.error(f"Ошибка распознавания: {e}")
            st.exception(e)

