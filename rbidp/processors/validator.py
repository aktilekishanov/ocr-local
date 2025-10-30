import json
from datetime import datetime, timedelta, timezone
import os
from typing import Dict, Any
import re
try:
    from rapidfuzz import fuzz  # type: ignore
except Exception:
    fuzz = None  # fuzzy matching optional; fallback to exact match
from rbidp.core.config import VALIDATION_FILENAME

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


def _norm_text(s: Any) -> str:
    if not isinstance(s, str):
        return ""
    # collapse whitespace and lowercase
    s = re.sub(r"\s+", " ", s.strip())
    return s.casefold()


def _parse_doc_date(s: Any):
    if not isinstance(s, str):
        return None
    s = s.strip()
    fmts = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except Exception:
            continue
    return None


def _now_utc_plus_5():
    tz = timezone(timedelta(hours=5))
    return datetime.now(tz)


def validate_run(meta_path: str, merged_path: str, output_dir: str, filename: str = VALIDATION_FILENAME) -> Dict[str, Any]:
    try:
        with open(meta_path, "r", encoding="utf-8") as mf:
            meta = json.load(mf)
        with open(merged_path, "r", encoding="utf-8") as gf:
            merged = json.load(gf)
    except Exception as e:
        return {"success": False, "error": f"IO error: {e}", "validation_path": "", "result": None}

    fio_meta = _norm_text(meta.get("fio")) if isinstance(meta, dict) else ""
    doc_type_meta = _norm_text(meta.get("doc_type")) if isinstance(meta, dict) else ""

    fio = _norm_text(merged.get("fio")) if isinstance(merged, dict) else ""
    doc_class = _norm_text(merged.get("doc_type")) if isinstance(merged, dict) else ""
    doc_date_raw = merged.get("doc_date") if isinstance(merged, dict) else None
    single_doc_type = merged.get("single_doc_type") if isinstance(merged, dict) else None

    # Fuzzy FIO match (token-sort) with threshold 90; fallback to exact match if rapidfuzz not available
    if fio_meta and fio:
        if fuzz is not None:
            try:
                score = fuzz.token_sort_ratio(fio_meta, fio)
                fio_match = score >= 90
            except Exception:
                fio_match = fio_meta == fio
        else:
            fio_match = fio_meta == fio
    else:
        fio_match = False
    doc_type_match = bool(doc_type_meta and doc_class and doc_type_meta == doc_class)

    d = _parse_doc_date(doc_date_raw)
    now = _now_utc_plus_5()
    doc_date_valid = False
    if d is not None:
        # assume doc date is local date at 00:00; compare inclusive 30 days window
        d_local = d.replace(tzinfo=timezone(timedelta(hours=5)))
        doc_date_valid = now <= (d_local + timedelta(days=30))

    single_doc_type_valid = bool(isinstance(single_doc_type, bool) and single_doc_type is True)

    checks = {
        "fio_match": fio_match,
        "doc_type_match": doc_type_match,
        "doc_date_valid": doc_date_valid,
        "single_doc_type_valid": single_doc_type_valid,
    }

    verdict = all(checks.values())

    # Minimal result payload
    result = {
        "checks": checks,
        "verdict": verdict,
    }

    try:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, filename)
        with open(out_path, "w", encoding="utf-8") as vf:
            json.dump(result, vf, ensure_ascii=False, indent=2)
        return {"success": True, "error": None, "validation_path": out_path, "result": result}
    except Exception as e:
        return {"success": False, "error": f"Write error: {e}", "validation_path": "", "result": result}
