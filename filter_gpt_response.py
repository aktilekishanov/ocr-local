import os
import json
from typing import Any, Dict, Optional


WANTED_KEYS = ["full_name", "doc_classification", "doc_date"]


def _try_parse_inner_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
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
                    inner = _try_parse_inner_json(content)
                    if isinstance(inner, dict):
                        return inner
            text = c0.get("text")
            if isinstance(text, str):
                inner = _try_parse_inner_json(text)
                if isinstance(inner, dict):
                    return inner
    # Some providers include direct top-level content
    content = obj.get("content")
    if isinstance(content, str):
        inner = _try_parse_inner_json(content)
        if isinstance(inner, dict):
            return inner
    return None


def _pick_wanted_keys(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (obj.get(k) if k in obj else None) for k in WANTED_KEYS}


def filter_gpt_response(input_path: str, output_dir: str, filename: str = "gpt_response_filtered.json") -> str:
    with open(input_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    parsed_candidates = []

    # Case 1: the file is a single JSON object or JSON string with the final object
    first = None
    try:
        first = json.loads(raw)
    except Exception:
        # Maybe it's a pure JSON string with braces (already our target)
        if raw and raw.lstrip().startswith("{") and raw.rstrip().endswith("}"):
            try:
                first = json.loads(raw)
            except Exception:
                first = None
        else:
            first = None

    if isinstance(first, dict):
        # Try as direct final JSON
        if all(k in first for k in WANTED_KEYS):
            parsed_candidates.append(first)
        # Try as provider response format
        inner = _extract_from_openai_like(first)
        if isinstance(inner, dict):
            parsed_candidates.append(inner)
    elif isinstance(first, str):
        inner = _try_parse_inner_json(first)
        if isinstance(inner, dict):
            parsed_candidates.append(inner)

    # Case 2: file may contain multiple JSON objects per line
    if not parsed_candidates:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    if all(k in obj for k in WANTED_KEYS):
                        parsed_candidates.append(obj)
                        continue
                    inner = _extract_from_openai_like(obj)
                    if isinstance(inner, dict):
                        parsed_candidates.append(inner)
                        continue
            except Exception:
                # maybe line is a JSON string with object content
                inner = _try_parse_inner_json(line)
                if isinstance(inner, dict):
                    parsed_candidates.append(inner)

    result_obj: Dict[str, Any]
    if parsed_candidates:
        # Prefer the first candidate that contains wanted keys
        for cand in parsed_candidates:
            if isinstance(cand, dict) and all(k in cand for k in WANTED_KEYS):
                result_obj = _pick_wanted_keys(cand)
                break
        else:
            result_obj = _pick_wanted_keys(parsed_candidates[0])
    else:
        result_obj = {k: None for k in WANTED_KEYS}

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result_obj, f, ensure_ascii=False, indent=2)
    return out_path


if __name__ == "__main__":
    default_input = os.path.join("output", "gpt_response_raw.json")
    default_output_dir = "output"
    print(filter_gpt_response(default_input, default_output_dir))
