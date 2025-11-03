import os
import re
import json
from datetime import datetime
from pathlib import Path
import uuid
import tempfile
import streamlit as st

from rbidp.clients.textract_client import ask_textract
from rbidp.processors.filter_textract_response import filter_textract_response
from rbidp.processors.filter_gpt_generic_response import filter_gpt_generic_response
from rbidp.processors.agent_extractor import extract_doc_data
from rbidp.processors.agent_doc_type_checker import check_single_doc_type
from rbidp.processors.merge_outputs import merge_extractor_and_doc_type
from rbidp.processors.validator import validate_run
from rbidp.core.config import (
    TEXTRACT_RAW,
    TEXTRACT_PAGES,
    GPT_DOC_TYPE_RAW,
    GPT_DOC_TYPE_FILTERED,
    GPT_EXTRACTOR_RAW,
    GPT_EXTRACTOR_FILTERED,
    MERGED_FILENAME,
    VALIDATION_FILENAME,
    METADATA_FILENAME,
)
from rbidp.orchestrator import run_pipeline
from rbidp.core.errors import message_for
try:
    import pypdf as _pypdf
except Exception:
    _pypdf = None
try:
    import PyPDF2 as _pypdf2
except Exception:
    _pypdf2 = None


def run_gpt_extractor(pages_obj: dict, gpt_dir: Path) -> dict:
    try:
        gpt_raw = extract_doc_data(pages_obj)
        raw_path = gpt_dir / GPT_EXTRACTOR_RAW
        try:
            with open(raw_path, "w", encoding="utf-8") as gf:
                gf.write(gpt_raw)
        except Exception:
            pass
        return {"success": True, "error": None, "raw_path": str(raw_path), "raw": gpt_raw}
    except Exception as e:
        return {"success": False, "error": str(e), "raw_path": "", "raw": ""}


def run_filter_gpt(raw_path: str, gpt_dir: Path) -> dict:
    try:
        filtered_path = filter_gpt_generic_response(str(raw_path), str(gpt_dir), filename=GPT_EXTRACTOR_FILTERED)
        with open(filtered_path, "r", encoding="utf-8") as ff:
            filtered_obj = json.load(ff)
        return {"success": True, "error": None, "filtered_path": filtered_path, "obj": filtered_obj}
    except Exception as e:
        try:
            with open(raw_path, "r", encoding="utf-8") as rf:
                raw_str = rf.read()
            try:
                raw_obj = json.loads(raw_str)
                return {"success": False, "error": str(e), "filtered_path": "", "obj": raw_obj, "raw": raw_str}
            except Exception:
                return {"success": False, "error": str(e), "filtered_path": "", "obj": None, "raw": raw_str}
        except Exception:
            return {"success": False, "error": str(e), "filtered_path": "", "obj": None, "raw": ""}


def run_doc_type_checker(pages_obj: dict, gpt_dir: Path) -> dict:
    try:
        raw = check_single_doc_type(pages_obj)
        raw_path = gpt_dir / GPT_DOC_TYPE_RAW
        try:
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(raw)
        except Exception:
            pass
        # Do not attempt to parse here; Forte GPT may return multiple JSON objects (e.g. "{}\n{}")
        return {"success": True, "error": None, "raw_path": str(raw_path), "raw": raw}
    except Exception as e:
        return {"success": False, "error": str(e), "raw_path": "", "raw": ""}


# --- Page setup ---
st.set_page_config(page_title="RB Loan Deferment IDP", layout="centered")

st.write("")
st.title("RB Loan Deferment IDP")
st.write("Загрузите один файл для распознавания (локальная обработка через Textract (Dev-OCR) & GPT (DMZ))")

# --- Basic paths ---
BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

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
        "Приказ о расторжении трудового договора",
        "Справка о расторжении трудового договора",
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


def _count_pdf_pages(path: str):
    try:
        if _pypdf is not None:
            reader = _pypdf.PdfReader(path)
            return len(reader.pages)
    except Exception:
        pass
    try:
        if _pypdf2 is not None:
            reader = _pypdf2.PdfReader(path)
            return len(reader.pages)
    except Exception:
        pass
    try:
        with open(path, "rb") as f:
            data = f.read()
        return len(re.findall(br"/Type\s*/Page\b", data)) or None
    except Exception:
        return None


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
        st.warning("Пожалуйста, прикрепите файл")
    elif reason == "Выберите причину":
        st.warning("Пожалуйста, выберите причину отсрочки")
    elif doc_type == "Выберите тип документа":
        st.warning("Пожалуйста, выберите тип документа")
    else:
        # Save uploaded file to a temporary location and call orchestrator once
        tmp_dir = tempfile.mkdtemp(prefix="upload_")
        tmp_path = Path(tmp_dir) / _safe_filename(uploaded_file.name)
        with open(tmp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        with st.spinner("Обрабатываем документ..."):
            result = run_pipeline(
                fio=fio or None,
                reason=reason,
                doc_type=doc_type,
                source_file_path=str(tmp_path),
                original_filename=uploaded_file.name,
                content_type=getattr(uploaded_file, "type", None),
                runs_root=RUNS_DIR,
            )

        st.subheader("Результат проверки")
        verdict = bool(result.get("verdict", False))
        errors = result.get("errors", []) or []

        if verdict:
            st.success("Вердикт: True — документ прошел проверку")
        else:
            st.error("Вердикт: False — документ не прошел проверку")

        if errors:
            st.markdown("**Ошибки**")
            for e in errors:
                code = e.get("code")
                msg = message_for(code) or e.get("message") or str(code)
                details = e.get("details")
                if details:
                    st.write(f"- {msg} — {details}")
                else:
                    st.write(f"- {msg}")

        # Diagnostics: show final_result.json for full context
        final_result_path = result.get("final_result_path")
        if isinstance(final_result_path, str) and os.path.exists(final_result_path):
            try:
                with open(final_result_path, "r", encoding="utf-8") as ff:
                    final_obj = json.load(ff)
                with st.expander("Диагностика: final_results.json"):
                    st.json(final_obj)
            except Exception:
                pass