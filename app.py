import os
import re
import json
from datetime import datetime
from pathlib import Path
import uuid
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
st.write("Загрузите один файл для распознавания (локальная обработка через Textract endpoint).")

# --- Basic paths ---
RUNS_DIR = Path("runs")
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
        with st.status("Сохраняем файл...", state="running", key="pipeline_status") as status:
            with open(saved_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            status.update(label=f"Файл сохранен: {saved_path}", state="complete")

        # DEBUG: file save
        print(f"[DEBUG] Saved upload to: {saved_path}")

        # Persist user input metadata early
        try:
            metadata = {
                "fio": fio or None,
                "reason": reason,
                "doc_type": doc_type,
            }
            with open(meta_dir / METADATA_FILENAME, "w", encoding="utf-8") as mf:
                json.dump(metadata, mf, ensure_ascii=False, indent=2)
            print(f"[DEBUG] Early metadata written to: {meta_dir / METADATA_FILENAME}")
        except Exception as e:
            print(f"[DEBUG] Failed to write early metadata: {e}")

        # Run Textract pipeline
        try:
            with st.status("Распознавание (Textract)...", state="running", key="pipeline_status") as status:
                textract_result = ask_textract(str(saved_path), output_dir=str(ocr_dir), save_json=True)
            # DEBUG: textract call result
            print(
                "[DEBUG] Textract result:",
                {
                    "success": textract_result.get("success"),
                    "error": textract_result.get("error"),
                    "raw_path": textract_result.get("raw_path"),
                },
            )

            # Step 1: Textract status
            if not textract_result.get("success"):
                err_msg = textract_result.get("error") or "OCR сервис вернул неуспешный статус."
                status.update(label=f"Ошибка распознавания: {err_msg}", state="error")
                st.error(f"Ошибка распознавания: {err_msg}")
                st.stop()
            try:
                status.update(label="Распознавание завершено", state="complete")
            except Exception:
                pass
            # DEBUG: textract success
            print("[DEBUG] Textract success: proceeding to filter_textract_response")

            # Step 2: Filter Textract into pages JSON
            filtered_textract_response_path = ""
            with st.status("Обработка страниц OCR...", state="running", key="pipeline_status") as status:
                try:
                    filtered_textract_response_path = filter_textract_response(textract_result.get("raw_obj", {}), str(ocr_dir), filename=TEXTRACT_PAGES)
                    # DEBUG: filter output path
                    print(f"[DEBUG] Filtered Textract written to: {filtered_textract_response_path}")
                except Exception as e:
                    status.update(label=f"Ошибка обработки страниц OCR: {e}", state="error")
                    st.error(f"Ошибка обработки страниц OCR: {e}")
                    # DEBUG: filter error
                    print(f"[DEBUG] Error in filter_textract_response: {e}")
                    st.stop()

                with open(filtered_textract_response_path, "r", encoding="utf-8") as f:
                    pages_obj = json.load(f)
                try:
                    status.update(label="Страницы OCR обработаны", state="complete")
                except Exception:
                    pass
            # DEBUG: pages stats
            try:
                _pages_len = len(pages_obj.get("pages", [])) if isinstance(pages_obj, dict) else None
            except Exception:
                _pages_len = None
            print(f"[DEBUG] pages_obj loaded. pages count: {_pages_len}")

            # Filter step status checks before proceeding to GPT
            if not isinstance(pages_obj, dict) or not isinstance(pages_obj.get("pages"), list):
                st.error("Ошибка: некорректный формат результатов OCR страниц.")
                st.stop()
            if len(pages_obj["pages"]) == 0:
                st.error("Ошибка: не удалось получить текст страниц из OCR.")
                # DEBUG: empty pages
                print("[DEBUG] No pages extracted from OCR")
                st.stop()

            # Doc type checker step (before GPT)
            # DEBUG: starting doc type checker
            print("[DEBUG] Starting doc type checker with pages_obj")
            with st.status("Проверка типа документа...", state="running", key="pipeline_status") as status:
                dtc_step = run_doc_type_checker(pages_obj, gpt_dir)
                if not dtc_step.get("success"):
                    status.update(label=f"Ошибка проверки типа документа: {dtc_step.get('error')}", state="error")
                    st.error(f"Ошибка проверки типа документа: {dtc_step.get('error')}")
                    # DEBUG: doc type checker error
                    print(f"[DEBUG] Doc type checker error: {dtc_step.get('error')}")
                    st.stop()
                else:
                    # Filter the doc type check raw into stable JSON (generic filter)
                    dtc_raw_path = dtc_step.get("raw_path")
                    try:
                        dtc_filtered_path = filter_gpt_generic_response(dtc_raw_path, str(gpt_dir), filename=GPT_DOC_TYPE_FILTERED)
                        # DEBUG: doc type filter success
                        print(f"[DEBUG] Doc type filter success. filtered_path={dtc_filtered_path}")
                        try:
                            status.update(label="Тип документа определен", state="complete")
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"[DEBUG] Doc type filter failed: {e}")
                        status.update(label=f"Ошибка фильтра doc_type_check: {e}", state="error")
                        st.error(f"Ошибка фильтра doc_type_check: {e}")
                        st.stop()

            # Run GPT steps when pages exist (no per-page preview UI)
            if isinstance(pages_obj.get("pages"), list) and len(pages_obj["pages"]) > 0:
                # DEBUG: starting GPT extractor
                print("[DEBUG] Starting GPT extractor with pages_obj")
                with st.status("GPT извлечение данных...", state="running", key="pipeline_status") as status_gpt:
                    gpt_step = run_gpt_extractor(pages_obj, gpt_dir)
                    if not gpt_step.get("success"):
                        status_gpt.update(label=f"Ошибка GPT: {gpt_step.get('error')}", state="error")
                        st.error(f"Ошибка GPT: {gpt_step.get('error')}")
                        # DEBUG: gpt extractor error
                        print(f"[DEBUG] GPT extractor error: {gpt_step.get('error')}")
                        st.stop()
                    filter_step = run_filter_gpt(gpt_step.get("raw_path", ""), gpt_dir)
                    if filter_step.get("success"):
                        fp = filter_step.get("filtered_path")
                        # DEBUG: gpt filter success
                        print(f"[DEBUG] GPT filter success. filtered_path={fp}")
                        try:
                            status_gpt.update(label="GPT извлечение завершено", state="complete")
                        except Exception:
                            pass
                    else:
                        status_gpt.update(label=f"Ошибка фильтрации GPT: {filter_step.get('error')}", state="error")
                        st.error(f"Ошибка фильтрации GPT: {filter_step.get('error')}")
                        st.stop()
                        # DEBUG: gpt filter failure
                        print("[DEBUG] GPT filter failed; showing fallback (obj or raw)")

                with st.status("Слияние результатов и валидация...", state="running", key="pipeline_status") as status_merge:
                    try:
                        merged_path = merge_extractor_and_doc_type(
                            extractor_filtered_path=fp,
                            doc_type_filtered_path=dtc_filtered_path,
                            output_dir=str(gpt_dir),
                            filename=MERGED_FILENAME,
                        )
                        with open(merged_path, "r", encoding="utf-8") as mf:
                            merged = json.load(mf)
                        # Validate merged.json against metadata.json
                        try:
                            validation = validate_run(
                                meta_path=str((base_dir / "meta" / "metadata.json")),
                                merged_path=str(merged_path),
                                output_dir=str(gpt_dir),
                                filename=VALIDATION_FILENAME,
                            )
                            if not validation.get("success"):
                                status_merge.update(label=f"Ошибка валидации: {validation.get('error')}", state="error")
                                st.error(f"Ошибка валидации: {validation.get('error')}")
                                st.stop()
                            val_result = validation.get("result", {})
                            validation_path = validation.get("validation_path", "")
                            st.subheader("Результат проверки")
                            st.json(val_result)
                            with open(merged_path, "rb") as mb:
                                st.download_button(
                                    label="Скачать JSON (итог)",
                                    data=mb.read(),
                                    file_name=MERGED_FILENAME,
                                    mime="application/json",
                                )
                            print(f"[DEBUG] Validation written to: {validation_path}")
                            try:
                                status_merge.update(label="Слияние и валидация завершены", state="complete")
                            except Exception:
                                pass
                        except Exception as ve:
                            status_merge.update(label=f"Ошибка валидации: {ve}", state="error")
                            st.error(f"Ошибка валидации: {ve}")
                            st.stop()
                        print(f"[DEBUG] Merged JSON written to: {merged_path}")
                    except Exception as me:
                        status_merge.update(label=f"Ошибка при формировании merged.json: {me}", state="error")
                        st.error(f"Ошибка при формировании merged.json: {me}")
                        st.stop()
            else:
                st.info("Нет распознанных страниц в результате.")
                # DEBUG: no pages to process
                print("[DEBUG] Skipping GPT: no pages to process")
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
                        "ocr_raw_path": str(ocr_dir / TEXTRACT_RAW),
                        "ocr_pages_filtered_path": str(filtered_textract_response_path or ""),
                        "gpt_doc_type_check_filtered_path": str(gpt_dir / GPT_DOC_TYPE_FILTERED),
                        "gpt_doc_type_check_path": str((gpt_dir / GPT_DOC_TYPE_RAW)),
                        "gpt_extractor_raw_path": str(gpt_dir / GPT_EXTRACTOR_RAW),
                        "gpt_extractor_filtered_path": str(gpt_dir / GPT_EXTRACTOR_FILTERED),
                        "gpt_merged_path": str(gpt_dir / MERGED_FILENAME),
                        "validation_path": str(gpt_dir / VALIDATION_FILENAME),
                    },
                    "status": "success",
                    "error": None,
                }
                with open(meta_dir / "manifest.json", "w", encoding="utf-8") as mf:
                    json.dump(manifest, mf, ensure_ascii=False, indent=2)
                # DEBUG: manifest written
                print(f"[DEBUG] Manifest written to: {meta_dir / 'manifest.json'}")
            except Exception:
                pass
        except Exception as e:
            st.error(f"Ошибка распознавания: {e}")
            # DEBUG: outer exception
            print(f"[DEBUG] Top-level processing error: {e}")
            st.exception(e)