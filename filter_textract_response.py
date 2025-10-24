
def filter_textract_response(obj: dict) -> str:
    data = obj.get("data", {})
    if isinstance(data, dict):
        if isinstance(data.get("text"), str):
            return data["text"]
        pages = data.get("pages")
        if isinstance(pages, list):
            return "\n\n".join(
                p.get("text", "") for p in pages if isinstance(p, dict)
            )

    blocks = obj.get("Blocks")
    if isinstance(blocks, list):
        has_line = any(
            isinstance(b, dict) and b.get("BlockType") == "LINE" for b in blocks
        )
        if has_line:
            return "\n".join(
                b.get("Text", "")
                for b in blocks
                if isinstance(b, dict) and b.get("BlockType") == "LINE"
            )
        return " ".join(
            b.get("Text", "")
            for b in blocks
            if isinstance(b, dict) and b.get("Text")
        )

    raise ValueError("Unsupported JSON structure: expected data.text, data.pages, or Textract Blocks")


