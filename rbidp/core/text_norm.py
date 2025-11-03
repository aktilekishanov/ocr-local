import re
from typing import Any, Optional
from rapidfuzz import fuzz


def fold_ws_case(s: Any) -> str:
    if not isinstance(s, str):
        return ""
    s2 = re.sub(r"\s+", " ", s.strip())
    return s2.casefold()


def kz_to_ru(s: str) -> str:
    table = str.maketrans({
        "қ": "к",
        "ұ": "у",
        "ү": "у",
        "ң": "н",
        "ғ": "г",
        "ө": "о",
        "Қ": "К",
        "Ұ": "У",
        "Ү": "У",
        "Ң": "Н",
        "Ғ": "Г",
        "Ө": "О",
    })
    return s.translate(table)


def latin_to_cyrillic(s: str) -> str:
    table = str.maketrans({
        "a": "а",
        "e": "е",
        "o": "о",
        "p": "р",
        "c": "с",
        "y": "у",
        "x": "х",
        "k": "к",
        "h": "н",
        "b": "в",
        "m": "м",
        "t": "т",
        "i": "и",
        "A": "А",
        "E": "Е",
        "O": "О",
        "P": "Р",
        "C": "С",
        "Y": "У",
        "X": "Х",
        "K": "К",
        "H": "Н",
        "B": "В",
        "M": "М",
        "T": "Т",
        "I": "И",
    })
    return s.translate(table)


def safe_fuzz_ratio(a: str, b: str) -> Optional[float]:
    try:
        return float(fuzz.token_sort_ratio(a, b))
    except Exception:
        return None


def normalize_fio(s: Any) -> str:
    """Normalize name-like strings for robust comparison."""
    s1 = fold_ws_case(s)
    s2 = kz_to_ru(s1)
    s3 = latin_to_cyrillic(s2)
    return s3
