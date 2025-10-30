import json
from datetime import datetime, timedelta, timezone
import os
from typing import Dict, Any
import re
from rbidp.core.config import VALIDATION_FILENAME
from rbidp.processors.filter_gpt_generic_response import filter_gpt_generic_response
from rbidp.clients.gpt_client import ask_gpt

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


PROMPT = (
    "You are a strict JSON validator. Compare two JSON objects: 'meta' and 'merged'.\n"
    "Return ONLY a minified JSON object with exact keys: {\"fio_match\": boolean, \"doc_type_match\": boolean, \"doc_date_valid\": boolean, \"single_doc_type_valid\": boolean}. No extra keys or text.\n"
    "Normalization rules: lowercase, trim, collapse whitespace.\n"
    "fio_match: true if meta.fio equals merged.fio after normalization; else false.\n"
    "doc_type_match: true if meta.doc_type equals merged.doc_type after normalization; else false.\n"
    "doc_date_valid: merged.doc_date is within 30 days from CURRENT_TIME (UTC+05:00), formats may be DD.MM.YYYY or YYYY-MM-DD or DD/MM/YYYY; else false.\n"
    "single_doc_type_valid: true if merged.single_doc_type is strictly true; else false.\n"
    "CURRENT_TIME: {CURRENT_TIME} (UTC+05:00).\n"
    "meta: {META}\n"
    "merged: {MERGED}\n"
)


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

    now = _now_utc_plus_5()
    prompt = PROMPT.format(
        CURRENT_TIME=now.isoformat(),
        META=json.dumps(meta, ensure_ascii=False),
        MERGED=json.dumps(merged, ensure_ascii=False),
    )
    os.makedirs(output_dir, exist_ok=True)
    gpt_raw = ask_gpt(prompt)
    try:
        raw_path = os.path.join(output_dir, "validation_gpt_raw.txt")
        with open(raw_path, "w", encoding="utf-8") as rf:
            rf.write(gpt_raw)
        filtered_path = filter_gpt_generic_response(raw_path, output_dir, filename="validation_gpt_filtered.json")
        with open(filtered_path, "r", encoding="utf-8") as ff:
            gpt_obj = json.load(ff)
    except Exception as e:
        return {"success": False, "error": f"Validation GPT parse error: {e}", "validation_path": "", "result": None}

    checks = {
        "fio_match": bool(gpt_obj.get("fio_match") is True),
        "doc_type_match": bool(gpt_obj.get("doc_type_match") is True),
        "doc_date_valid": bool(gpt_obj.get("doc_date_valid") is True),
        "single_doc_type_valid": bool(gpt_obj.get("single_doc_type_valid") is True),
    }

    verdict = all(checks.values())

    # Minimal result payload
    result = {
        "checks": checks,
        "verdict": verdict,
    }

    try:
        out_path = os.path.join(output_dir, filename)
        with open(out_path, "w", encoding="utf-8") as vf:
            json.dump(result, vf, ensure_ascii=False, indent=2)
        return {"success": True, "error": None, "validation_path": out_path, "result": result}
    except Exception as e:
        return {"success": False, "error": f"Write error: {e}", "validation_path": "", "result": result}
