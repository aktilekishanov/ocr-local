import json
from datetime import datetime, timedelta
import os
from typing import Dict, Any
from rbidp.core.config import VALIDATION_FILENAME
from rbidp.core.dates import parse_doc_date, now_utc_plus
from rbidp.core.text_norm import fold_ws_case, safe_fuzz_ratio, normalize_fio

VALIDATION_MESSAGES = {
    "checks": {
        "fio_match": {
            True: "Относится к заявителю",
            False: "Не относится к заявителю",
        },
        "doc_type_match": {
            True: "Верный формат документа",
            False: "Неверный формат документа",
        },
        "doc_date_valid": {
            True: "Актуальная дата документа",
            False: "Устаревшая дата документа",
        },
        "single_doc_type_valid": {
            True: "Файл содержит один тип документа",
            False: "Файл содержит несколько типов документов",
        },
    },
    "verdict": {
        True: "Отсрочка активирована: прикрепленный документ успешно прошел проверку",
        False: "К сожалению, Вам отказано в отсрочке: прикрепленный документ не прошел проверку",
    },
}


def _now_utc_plus_5():
    return now_utc_plus(5)

def validate_run(meta_path: str, merged_path: str, output_dir: str, filename: str = VALIDATION_FILENAME, write_file: bool = True) -> Dict[str, Any]:
    try:
        with open(meta_path, "r", encoding="utf-8") as mf:
            meta = json.load(mf)
        with open(merged_path, "r", encoding="utf-8") as gf:
            merged = json.load(gf)
    except Exception as e:
        return {"success": False, "error": f"IO error: {e}", "validation_path": "", "result": None}


    # Inputs (raw)
    fio_meta_raw = meta.get("fio") if isinstance(meta, dict) else None
    doc_type_meta_raw = meta.get("doc_type") if isinstance(meta, dict) else None
    fio_raw = merged.get("fio") if isinstance(merged, dict) else None
    doc_class = merged.get("doc_type") if isinstance(merged, dict) else None
    doc_date_raw = merged.get("doc_date") if isinstance(merged, dict) else None
    single_doc_type_raw = merged.get("single_doc_type") if isinstance(merged, dict) else None

    # Normalization (FIO)
    fio_meta_norm = normalize_fio(fio_meta_raw)
    fio_norm = normalize_fio(fio_raw)

    # Doc type (meta folded for safety, extracted kept raw)
    doc_type_meta = fold_ws_case(doc_type_meta_raw)

    # Similarity scores (pre/post normalization)
    score_before = (
        safe_fuzz_ratio(fold_ws_case(fio_meta_raw), fold_ws_case(fio_raw))
        if (fio_meta_raw and fio_raw)
        else None
    )
    score_after = safe_fuzz_ratio(fio_meta_norm, fio_norm) if (fio_meta_norm and fio_norm) else None

    if fio_meta_norm and fio_norm:
        score = safe_fuzz_ratio(fio_meta_norm, fio_norm)
        if score is not None:
            fio_match = score >= 90
        else:
            fio_match = fio_meta_norm == fio_norm
    else:
        fio_match = None
    if doc_type_meta and doc_class:
        doc_type_match = doc_type_meta == doc_class
    else:
        doc_type_match = None

    d = parse_doc_date(doc_date_raw)
    now = _now_utc_plus_5()
    if d is None:
        doc_date_valid = None
    else:
        d_local = d.replace(tzinfo=now.tzinfo)
        doc_date_valid = now <= (d_local + timedelta(days=30))

    if isinstance(single_doc_type_raw, bool):
        single_doc_type_valid = single_doc_type_raw
    else:
        single_doc_type_valid = None

    checks = {
        "fio_match": fio_match,
        "doc_type_match": doc_type_match,
        "doc_date_valid": doc_date_valid,
        "single_doc_type_valid": single_doc_type_valid,
    }

    verdict = (
        checks.get("fio_match") is True
        and checks.get("doc_type_match") is True
        and checks.get("doc_date_valid") is True
        and checks.get("single_doc_type_valid") is True
    )

    diagnostics = {
        "inputs": {
            "fio_meta": fio_meta_raw,
            "fio": fio_raw,
            "doc_type_meta": doc_type_meta_raw,
            "doc_type": doc_class_raw,
            "doc_date": doc_date_raw,
            "single_doc_type": single_doc_type_raw,
        },
        "normalization": {
            "fio_meta_norm": fio_meta_norm,
            "fio_norm": fio_norm,
            "doc_type_meta_norm": doc_type_meta,
            "doc_type_norm": doc_class,
        },
        "scores": {
            "fio_similarity_before": score_before,
            "fio_similarity_after": score_after,
        },
        "timing": {
            "now_utc_plus_5": now.isoformat(),
            "doc_date_parsed": d.isoformat() if d else None,
            "validity_window_days": 30,
        },
        "checks": checks,
        "messages": {
            key: VALIDATION_MESSAGES["checks"][key].get(val) if val is not None else None
            for key, val in checks.items()
        },
    }

    result = {
        "checks": checks,
        "verdict": verdict,
        "diagnostics": diagnostics,
    }

    if not write_file:
        return {"success": True, "error": None, "validation_path": "", "result": result}
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        return {"success": False, "error": f"Validation error: {e}", "validation_path": "", "result": None}