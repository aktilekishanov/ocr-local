import os
import re
import json
from datetime import datetime
from pathlib import Path
import uuid
import streamlit as st

from rbidp.clients.textract_client import ask_textract
from rbidp.processors.filter_textract_response import filter_textract_response
from rbidp.processors.filter_gpt_response import filter_gpt_response
from rbidp.processors.agent_extractor import extract_doc_data


def run_gpt_extractor(pages_obj: dict, gpt_dir: Path) -> dict:
    try:
        gpt_raw = extract_doc_data(pages_obj)
        raw_path = gpt_dir / "gpt_response_raw.json"
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
        filtered_path = filter_gpt_response(str(raw_path), str(gpt_dir))
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


# --- Page setup ---
st.set_page_config(page_title="RB Loan Deferment IDP", layout="centered")

st.write("")
st.title("RB Loan Deferment IDP")
st.write("Загрузите один файл для распознавания (локальная обработка через Textract endpoint).")

# --- Basic paths ---
INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")
RUNS_DIR = Path("runs")
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
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
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_id = uuid.uuid4().hex[:5]
        date_str = datetime.now().strftime("%Y-%m-%d")
        run_id = f"{ts}_{short_id}"
        base_dir = RUNS_DIR / date_str / run_id
        input_dir = base_dir / "input" / "original"
        ocr_dir = base_dir / "ocr"
        gpt_dir = base_dir / "gpt"
        meta_dir = base_dir / "meta"
        for d in (input_dir, ocr_dir, gpt_dir, meta_dir):
            d.mkdir(parents=True, exist_ok=True)

        base = _safe_filename(uploaded_file.name)
        saved_path = input_dir / base
        with open(saved_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.info(f"Файл сохранен: {saved_path}")

        # Run Textract pipeline
        try:
            textract_result = ask_textract(str(saved_path), output_dir=str(ocr_dir), save_json=True)

            # Step 1: Textract status
            if not textract_result.get("success"):
                err_msg = textract_result.get("error") or "OCR сервис вернул неуспешный статус."
                st.error(f"Ошибка распознавания: {err_msg}")
                st.stop()

            st.success("Распознавание завершено.")

            # Step 2: Filter Textract into pages JSON
            pages_path = ""
            try:
                pages_path = filter_textract_response(textract_result.get("raw_obj", {}), str(ocr_dir), filename="textract_response_filtered.json")
            except Exception as e:
                st.error(f"Ошибка обработки страниц OCR: {e}")
                st.stop()

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
                if pages_obj:
                    gpt_step = run_gpt_extractor(pages_obj, gpt_dir)
                    if not gpt_step.get("success"):
                        st.error(f"Ошибка GPT: {gpt_step.get('error')}")
                        st.stop()
                    filter_step = run_filter_gpt(gpt_step.get("raw_path", ""), gpt_dir)
                    if filter_step.get("success"):
                        st.json(filter_step.get("obj"))
                        fp = filter_step.get("filtered_path")
                        if fp:
                            with open(fp, "rb") as ff:
                                st.download_button(
                                    label="Скачать JSON (фильтрованный результат)",
                                    data=ff.read(),
                                    file_name=os.path.basename(fp),
                                    mime="application/json",
                                )
                    else:
                        obj = filter_step.get("obj")
                        raw = filter_step.get("raw", "")
                        if isinstance(obj, dict):
                            st.json(obj)
                        elif raw:
                            st.code(raw, language="json")
            else:
                st.info("Нет распознанных страниц в результате.")
            try:
                manifest = {
                    "run_id": run_id,
                    "created_at": datetime.now().isoformat(),
                    "user_input": {
                        "fio": fio or None,
                        "reason": reason,
                        "doc_type": doc_type,
                    },
                    "file": {
                        "original_filename": uploaded_file.name,
                        "saved_path": str(saved_path),
                        "content_type": getattr(uploaded_file, "type", None),
                        "size_bytes": saved_path.stat().st_size if saved_path.exists() else None,
                    },
                    "processing": {
                        "ocr_engine": "textract",
                        "ocr_raw_path": str(ocr_dir / "textract_response_raw.json"),
                        "ocr_pages_filtered_path": str(pages_path or ""),
                        "gpt_raw_path": str(gpt_dir / "gpt_response_raw.json"),
                        "gpt_filtered_path": str(gpt_dir / "gpt_response_filtered.json"),
                    },
                    "status": "success",
                    "error": None,
                }
                with open(meta_dir / "manifest.json", "w", encoding="utf-8") as mf:
                    json.dump(manifest, mf, ensure_ascii=False, indent=2)
            except Exception:
                pass
        except Exception as e:
            st.error(f"Ошибка распознавания: {e}")
            st.exception(e)