import os
import re
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from rbidp.clients.textract_client import ask_textract
from rbidp.processors.filter_textract_response import filter_textract_response
from rbidp.processors.agent_doc_type_checker import check_single_doc_type
from rbidp.processors.agent_extractor import extract_doc_data
from rbidp.processors.filter_gpt_generic_response import filter_gpt_generic_response
from rbidp.processors.merge_outputs import merge_extractor_and_doc_type
from rbidp.processors.validator import validate_run
from rbidp.core.errors import make_error
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


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\-\.\s]", "_", (name or "").strip())
    name = re.sub(r"\s+", "_", name)
    return name or "file"


def _count_pdf_pages(path: str) -> Optional[int]:
    try:
        import pypdf as _pypdf  # type: ignore
        try:
            reader = _pypdf.PdfReader(path)
            return len(reader.pages)
        except Exception:
            pass
    except Exception:
        pass
    try:
        import PyPDF2 as _pypdf2  # type: ignore
        try:
            reader = _pypdf2.PdfReader(path)
            return len(reader.pages)
        except Exception:
            pass
    except Exception:
        pass
    try:
        with open(path, "rb") as f:
            data = f.read()
        import re as _re
        return len(_re.findall(br"/Type\s*/Page\b", data)) or None
    except Exception:
        return None


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _now_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:5]
    return f"{ts}_{short_id}"


def _mk_run_dirs(runs_root: Path, run_id: str) -> Dict[str, Path]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_dir = runs_root / date_str / run_id
    input_dir = base_dir / "input" / "original"
    ocr_dir = base_dir / "ocr"
    gpt_dir = base_dir / "gpt"
    meta_dir = base_dir / "meta"
    for d in (input_dir, ocr_dir, gpt_dir, meta_dir):
        d.mkdir(parents=True, exist_ok=True)
    return {
        "base": base_dir,
        "input": input_dir,
        "ocr": ocr_dir,
        "gpt": gpt_dir,
        "meta": meta_dir,
    }


def _build_final(
    run_id: str,
    errors: List[Dict[str, Any]],
    verdict: bool,
    checks: Optional[Dict[str, Any]],
    artifacts: Dict[str, str],
    final_path: Path,
) -> Dict[str, Any]:
    artifacts = dict(artifacts)
    artifacts.setdefault("final_result_path", str(final_path))
    result = {
        "run_id": run_id,
        "verdict": bool(verdict),
        "errors": errors,
        "checks": checks,
        "artifacts": artifacts,
    }
    _write_json(final_path, result)
    return result


def run_pipeline(
    fio: Optional[str],
    reason: Optional[str],
    doc_type: str,
    source_file_path: str,
    original_filename: str,
    content_type: Optional[str],
    runs_root: Path,
) -> Dict[str, Any]:
    run_id = _now_id()
    dirs = _mk_run_dirs(runs_root, run_id)
    base_dir, input_dir, ocr_dir, gpt_dir, meta_dir = (
        dirs["base"], dirs["input"], dirs["ocr"], dirs["gpt"], dirs["meta"]
    )

    errors: List[Dict[str, Any]] = []
    artifacts: Dict[str, str] = {}

    base_name = _safe_filename(original_filename or os.path.basename(source_file_path))
    saved_path = input_dir / base_name
    try:
        shutil.copyfile(source_file_path, saved_path)
    except Exception as e:
        errors.append(make_error("FILE_SAVE_FAILED", details=str(e)))
        final_path = meta_dir / "final_result.json"
        result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
        manifest = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
            "file": {
                "original_filename": original_filename,
                "saved_path": str(saved_path),
                "content_type": content_type,
                "size_bytes": None,
            },
            "processing": {},
            "status": "error",
            "error": "FILE_SAVE_FAILED",
            "final_result_path": str(final_path),
        }
        _write_json(meta_dir / "manifest.json", manifest)
        return result

    size_bytes = None
    try:
        size_bytes = saved_path.stat().st_size
    except Exception:
        pass

    metadata = {"fio": fio or None, "reason": reason, "doc_type": doc_type}
    _write_json(meta_dir / METADATA_FILENAME, metadata)

    if saved_path.suffix.lower() == ".pdf":
        pages = _count_pdf_pages(str(saved_path))
        if pages is not None and pages > 3:
            errors.append(make_error("PDF_TOO_MANY_PAGES"))
            final_path = meta_dir / "final_result.json"
            result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
            manifest = {
                "run_id": run_id,
                "created_at": datetime.now().isoformat(),
                "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
                "file": {
                    "original_filename": original_filename,
                    "saved_path": str(saved_path),
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                },
                "processing": {},
                "status": "error",
                "error": "PDF_TOO_MANY_PAGES",
                "final_result_path": str(final_path),
            }
            _write_json(meta_dir / "manifest.json", manifest)
            return result

    # OCR
    textract_result = ask_textract(str(saved_path), output_dir=str(ocr_dir), save_json=True)
    artifacts["ocr_raw_path"] = str(ocr_dir / TEXTRACT_RAW)
    if not textract_result.get("success"):
        errors.append(make_error("OCR_FAILED", details=str(textract_result.get("error"))) )
        final_path = meta_dir / "final_result.json"
        result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
        manifest = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
            "file": {
                "original_filename": original_filename,
                "saved_path": str(saved_path),
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
            "processing": {"ocr_engine": "textract"},
            "status": "error",
            "error": "OCR_FAILED",
            "final_result_path": str(final_path),
        }
        _write_json(meta_dir / "manifest.json", manifest)
        return result

    # Filter OCR pages
    try:
        filtered_pages_path = filter_textract_response(textract_result.get("raw_obj", {}), str(ocr_dir), filename=TEXTRACT_PAGES)
        artifacts["ocr_pages_filtered_path"] = str(filtered_pages_path)
        with open(filtered_pages_path, "r", encoding="utf-8") as f:
            pages_obj = json.load(f)
        if not isinstance(pages_obj, dict) or not isinstance(pages_obj.get("pages"), list):
            raise ValueError("Invalid pages object")
        if len(pages_obj["pages"]) == 0:
            errors.append(make_error("OCR_EMPTY_PAGES"))
            final_path = meta_dir / "final_result.json"
            result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
            manifest = {
                "run_id": run_id,
                "created_at": datetime.now().isoformat(),
                "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
                "file": {
                    "original_filename": original_filename,
                    "saved_path": str(saved_path),
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                },
                "processing": {
                    "ocr_engine": "textract",
                    "ocr_raw_path": str(ocr_dir / TEXTRACT_RAW),
                    "ocr_pages_filtered_path": str(filtered_pages_path),
                },
                "status": "error",
                "error": "OCR_EMPTY_PAGES",
                "final_result_path": str(final_path),
            }
            _write_json(meta_dir / "manifest.json", manifest)
            return result
    except Exception as e:
        errors.append(make_error("OCR_FILTER_FAILED", details=str(e)))
        final_path = meta_dir / "final_result.json"
        result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
        manifest = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
            "file": {
                "original_filename": original_filename,
                "saved_path": str(saved_path),
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
            "processing": {"ocr_engine": "textract"},
            "status": "error",
            "error": "OCR_FILTER_FAILED",
            "final_result_path": str(final_path),
        }
        _write_json(meta_dir / "manifest.json", manifest)
        return result

    # Doc type checker (GPT)
    try:
        dtc_raw_str = check_single_doc_type(pages_obj)
        dtc_raw_path = gpt_dir / GPT_DOC_TYPE_RAW
        with open(dtc_raw_path, "w", encoding="utf-8") as f:
            f.write(dtc_raw_str or "")
        artifacts["gpt_doc_type_check_path"] = str(dtc_raw_path)
        dtc_filtered_path = filter_gpt_generic_response(str(dtc_raw_path), str(gpt_dir), filename=GPT_DOC_TYPE_FILTERED)
        artifacts["gpt_doc_type_check_filtered_path"] = str(dtc_filtered_path)
        with open(dtc_filtered_path, "r", encoding="utf-8") as f:
            dtc_obj = json.load(f)
        is_single = dtc_obj.get("single_doc_type") if isinstance(dtc_obj, dict) else None
        if not isinstance(is_single, bool):
            errors.append(make_error("DTC_PARSE_ERROR"))
            final_path = meta_dir / "final_result.json"
            result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
            _write_json(meta_dir / "manifest.json", {
                "run_id": run_id,
                "created_at": datetime.now().isoformat(),
                "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
                "file": {
                    "original_filename": original_filename,
                    "saved_path": str(saved_path),
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                },
                "processing": {
                    "ocr_engine": "textract",
                    "ocr_raw_path": str(ocr_dir / TEXTRACT_RAW),
                    "ocr_pages_filtered_path": str(artifacts.get("ocr_pages_filtered_path", "")),
                    "gpt_doc_type_check_path": str(dtc_raw_path),
                    "gpt_doc_type_check_filtered_path": str(dtc_filtered_path),
                },
                "status": "error",
                "error": "DTC_PARSE_ERROR",
                "final_result_path": str(final_path),
            })
            return result
        if is_single is False:
            errors.append(make_error("MULTIPLE_DOCUMENTS"))
            final_path = meta_dir / "final_result.json"
            result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
            _write_json(meta_dir / "manifest.json", {
                "run_id": run_id,
                "created_at": datetime.now().isoformat(),
                "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
                "file": {
                    "original_filename": original_filename,
                    "saved_path": str(saved_path),
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                },
                "processing": {
                    "ocr_engine": "textract",
                    "ocr_raw_path": str(ocr_dir / TEXTRACT_RAW),
                    "ocr_pages_filtered_path": str(artifacts.get("ocr_pages_filtered_path", "")),
                    "gpt_doc_type_check_path": str(dtc_raw_path),
                    "gpt_doc_type_check_filtered_path": str(dtc_filtered_path),
                },
                "status": "error",
                "error": "MULTIPLE_DOCUMENTS",
                "final_result_path": str(final_path),
            })
            return result
    except Exception as e:
        errors.append(make_error("DTC_FAILED", details=str(e)))
        final_path = meta_dir / "final_result.json"
        result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
        _write_json(meta_dir / "manifest.json", {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
            "file": {
                "original_filename": original_filename,
                "saved_path": str(saved_path),
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
            "processing": {"ocr_engine": "textract"},
            "status": "error",
            "error": "DTC_FAILED",
            "final_result_path": str(final_path),
        })
        return result

    # Extraction (GPT)
    try:
        gpt_raw = extract_doc_data(pages_obj)
        gpt_raw_path = gpt_dir / GPT_EXTRACTOR_RAW
        with open(gpt_raw_path, "w", encoding="utf-8") as f:
            f.write(gpt_raw or "")
        artifacts["gpt_extractor_raw_path"] = str(gpt_raw_path)

        filtered_path = filter_gpt_generic_response(str(gpt_raw_path), str(gpt_dir), filename=GPT_EXTRACTOR_FILTERED)
        artifacts["gpt_extractor_filtered_path"] = str(filtered_path)
        with open(filtered_path, "r", encoding="utf-8") as f:
            filtered_obj = json.load(f)
        # schema check
        if not isinstance(filtered_obj, dict):
            raise ValueError("Extractor filtered object is not a dict")
        for k in ("fio", "doc_type", "doc_date"):
            if k not in filtered_obj:
                raise ValueError("Missing key: " + k)
            v = filtered_obj[k]
            if v is not None and not isinstance(v, str):
                raise ValueError(f"Key {k} has invalid type")
    except ValueError as ve:
        errors.append(make_error("EXTRACT_SCHEMA_INVALID", details=str(ve)))
        final_path = meta_dir / "final_result.json"
        result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
        _write_json(meta_dir / "manifest.json", {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
            "file": {
                "original_filename": original_filename,
                "saved_path": str(saved_path),
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
            "processing": {
                "ocr_engine": "textract",
                "ocr_raw_path": str(ocr_dir / TEXTRACT_RAW),
                "ocr_pages_filtered_path": str(artifacts.get("ocr_pages_filtered_path", "")),
                "gpt_doc_type_check_filtered_path": artifacts.get("gpt_doc_type_check_filtered_path", ""),
                "gpt_doc_type_check_path": artifacts.get("gpt_doc_type_check_path", ""),
            },
            "status": "error",
            "error": "EXTRACT_SCHEMA_INVALID",
            "final_result_path": str(final_path),
        })
        return result
    except Exception as e:
        errors.append(make_error("EXTRACT_FAILED", details=str(e)))
        final_path = meta_dir / "final_result.json"
        result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
        _write_json(meta_dir / "manifest.json", {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
            "file": {
                "original_filename": original_filename,
                "saved_path": str(saved_path),
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
            "processing": {"ocr_engine": "textract"},
            "status": "error",
            "error": "EXTRACT_FAILED",
            "final_result_path": str(final_path),
        })
        return result

    # Merge
    try:
        merged_path = merge_extractor_and_doc_type(
            extractor_filtered_path=artifacts.get("gpt_extractor_filtered_path", ""),
            doc_type_filtered_path=artifacts.get("gpt_doc_type_check_filtered_path", ""),
            output_dir=str(gpt_dir),
            filename=MERGED_FILENAME,
        )
        artifacts["gpt_merged_path"] = str(merged_path)
    except Exception as e:
        errors.append(make_error("MERGE_FAILED", details=str(e)))
        final_path = meta_dir / "final_result.json"
        result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
        _write_json(meta_dir / "manifest.json", {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
            "file": {
                "original_filename": original_filename,
                "saved_path": str(saved_path),
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
            "processing": {"ocr_engine": "textract"},
            "status": "error",
            "error": "MERGE_FAILED",
            "final_result_path": str(final_path),
        })
        return result

    # Validation
    try:
        validation = validate_run(
            meta_path=str(meta_dir / METADATA_FILENAME),
            merged_path=str(artifacts.get("gpt_merged_path", "")),
            output_dir=str(gpt_dir),
            filename=VALIDATION_FILENAME,
        )
        artifacts["validation_path"] = str(gpt_dir / VALIDATION_FILENAME)
        if not validation.get("success"):
            errors.append(make_error("VALIDATION_FAILED", details=str(validation.get("error"))))
            final_path = meta_dir / "final_result.json"
            result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
            _write_json(meta_dir / "manifest.json", {
                "run_id": run_id,
                "created_at": datetime.now().isoformat(),
                "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
                "file": {
                    "original_filename": original_filename,
                    "saved_path": str(saved_path),
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                },
                "processing": {
                    "ocr_engine": "textract",
                    "ocr_raw_path": str(ocr_dir / TEXTRACT_RAW),
                    "ocr_pages_filtered_path": str(artifacts.get("ocr_pages_filtered_path", "")),
                    "gpt_doc_type_check_filtered_path": artifacts.get("gpt_doc_type_check_filtered_path", ""),
                    "gpt_doc_type_check_path": artifacts.get("gpt_doc_type_check_path", ""),
                    "gpt_extractor_raw_path": artifacts.get("gpt_extractor_raw_path", ""),
                    "gpt_extractor_filtered_path": artifacts.get("gpt_extractor_filtered_path", ""),
                    "gpt_merged_path": artifacts.get("gpt_merged_path", ""),
                    "validation_path": artifacts.get("validation_path", ""),
                },
                "status": "error",
                "error": "VALIDATION_FAILED",
                "final_result_path": str(final_path),
            })
            return result

        val_result = validation.get("result", {})
        checks = val_result.get("checks") if isinstance(val_result, dict) else None
        verdict = bool(val_result.get("verdict")) if isinstance(val_result, dict) else False
        check_errors: List[Dict[str, Any]] = []
        if isinstance(checks, dict):
            if checks.get("fio_match") is False:
                check_errors.append(make_error("FIO_MISMATCH"))
            if checks.get("doc_type_match") is False:
                check_errors.append(make_error("DOC_TYPE_MISMATCH"))
            dv = checks.get("doc_date_valid")
            if dv is False:
                check_errors.append(make_error("DOC_DATE_TOO_OLD"))
            elif dv is None:
                check_errors.append(make_error("DOC_DATE_PARSE_FAILED"))
            if checks.get("single_doc_type_valid") is False:
                check_errors.append(make_error("SINGLE_DOC_TYPE_INVALID"))
        errors.extend(check_errors)

        final_path = meta_dir / "final_result.json"
        result = _build_final(run_id, errors, verdict=verdict, checks=checks, artifacts=artifacts, final_path=final_path)

        manifest = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
            "file": {
                "original_filename": original_filename,
                "saved_path": str(saved_path),
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
            "processing": {
                "ocr_engine": "textract",
                "ocr_raw_path": str(ocr_dir / TEXTRACT_RAW),
                "ocr_pages_filtered_path": str(artifacts.get("ocr_pages_filtered_path", "")),
                "gpt_doc_type_check_filtered_path": artifacts.get("gpt_doc_type_check_filtered_path", ""),
                "gpt_doc_type_check_path": artifacts.get("gpt_doc_type_check_path", ""),
                "gpt_extractor_raw_path": artifacts.get("gpt_extractor_raw_path", ""),
                "gpt_extractor_filtered_path": artifacts.get("gpt_extractor_filtered_path", ""),
                "gpt_merged_path": artifacts.get("gpt_merged_path", ""),
                "validation_path": artifacts.get("validation_path", ""),
            },
            "status": "success",
            "error": None,
            "final_result_path": str(final_path),
        }
        _write_json(meta_dir / "manifest.json", manifest)
        return result
    except Exception as e:
        errors.append(make_error("VALIDATION_FAILED", details=str(e)))
        final_path = meta_dir / "final_result.json"
        result = _build_final(run_id, errors, verdict=False, checks=None, artifacts=artifacts, final_path=final_path)
        _write_json(meta_dir / "manifest.json", {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "user_input": {"fio": fio or None, "reason": reason, "doc_type": doc_type},
            "file": {
                "original_filename": original_filename,
                "saved_path": str(saved_path),
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
            "processing": {
                "ocr_engine": "textract",
                "ocr_raw_path": str(ocr_dir / TEXTRACT_RAW),
                "ocr_pages_filtered_path": str(artifacts.get("ocr_pages_filtered_path", "")),
                "gpt_doc_type_check_filtered_path": artifacts.get("gpt_doc_type_check_filtered_path", ""),
                "gpt_doc_type_check_path": artifacts.get("gpt_doc_type_check_path", ""),
                "gpt_extractor_raw_path": artifacts.get("gpt_extractor_raw_path", ""),
                "gpt_extractor_filtered_path": artifacts.get("gpt_extractor_filtered_path", ""),
                "gpt_merged_path": artifacts.get("gpt_merged_path", ""),
                "validation_path": artifacts.get("validation_path", ""),
            },
            "status": "error",
            "error": "VALIDATION_FAILED",
            "final_result_path": str(final_path),
        })
        return result
