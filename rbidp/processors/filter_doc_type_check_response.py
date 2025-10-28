import os
import json
from typing import Any, Dict, Optional


def _try_parse_bool_obj(text: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "single_doc_type" in obj:
            val = obj.get("single_doc_type")
            if isinstance(val, bool):
                return {"single_doc_type": val}
            # allow truthy/falsy coercion if provider returns strings
            if isinstance(val, str):
                low = val.strip().lower()
                if low in ("true", "false"):
                    return {"single_doc_type": (low == "true")}
        # sometimes providers return the final JSON as a string
        if isinstance(obj, str):
            inner = _try_parse_bool_obj(obj)
            if inner is not None:
                return inner
    except Exception:
        return None
    return None


def _extract_from_openai_like(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    choices = obj.get("choices")
    if isinstance(choices, list) and choices:
        c0 = choices[0]
        if isinstance(c0, dict):
            msg = c0.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str):
                    inner = _try_parse_bool_obj(content)
                    if inner is not None:
                        return inner
            text = c0.get("text")
            if isinstance(text, str):
                inner = _try_parse_bool_obj(text)
                if inner is not None:
                    return inner
    content = obj.get("content")
    if isinstance(content, str):
        inner = _try_parse_bool_obj(content)
        if inner is not None:
            return inner
    return None


def filter_doc_type_check_response(input_path: str, output_dir: str, filename: str = "doc_type_check_filtered.json") -> str:
    with open(input_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    result_obj: Dict[str, Any] = {"single_doc_type": None}

    # Case 1: try parse entire content as JSON or JSON-string
    first = None
    try:
        first = json.loads(raw)
    except Exception:
        if raw and raw.lstrip().startswith("{") and raw.rstrip().endswith("}"):
            try:
                first = json.loads(raw)
            except Exception:
                first = None
        else:
            first = None

    if isinstance(first, dict):
        direct = _try_parse_bool_obj(raw)
        if direct is not None:
            result_obj = direct
        else:
            inner = _extract_from_openai_like(first)
            if inner is not None:
                result_obj = inner
    elif isinstance(first, str):
        inner = _try_parse_bool_obj(first)
        if inner is not None:
            result_obj = inner

    # Case 2: multi-line responses like "{}\n{}"
    if result_obj.get("single_doc_type") is None:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    inner = _try_parse_bool_obj(json.dumps(obj, ensure_ascii=False))
                    if inner is not None:
                        result_obj = inner
                        break
            except Exception:
                inner = _try_parse_bool_obj(line)
                if inner is not None:
                    result_obj = inner
                    break

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result_obj, f, ensure_ascii=False, indent=2)
    return out_path
