import urllib.request
import ssl
import mimetypes
import os
import uuid
import json
from typing import Optional
from rbidp.processors.image_to_pdf_converter import convert_image_to_pdf
 
def call_fortebank_textract(pdf_path: str, ocr_engine: str = "textract") -> str:
    """
    Sends a PDF to ForteBank Textract OCR endpoint and returns the raw response.
    """
    url = "https://dev-ocr.fortebank.com/v1/pdf"
 
    # Read file bytes
    with open(pdf_path, "rb") as f:
        file_data = f.read()
 
    # Prepare multipart/form-data body manually
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    content_type = f"multipart/form-data; boundary={boundary}"
 
    filename = os.path.basename(pdf_path)
    mime_type = mimetypes.guess_type(filename)[0] or "application/pdf"
    if not mime_type or not mime_type.endswith("pdf"):
        mime_type = "application/pdf"
 
    # Construct the multipart body
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="pdf"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + file_data + b"\r\n" + (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="ocr"\r\n\r\n'
        f"{ocr_engine}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
 
    # Prepare request
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    req.add_header("Accept", "*/*")
 
    # For dev servers (non-SSL)
    context = ssl._create_unverified_context()
 
    with urllib.request.urlopen(req, context=context) as response:
        result = response.read().decode("utf-8")
 
    return result

def ask_textract(pdf_path: str, output_dir: str = "output", save_json: bool = True) -> dict:
    work_path = pdf_path
    temp_pdf: Optional[str] = None
    mt, _ = mimetypes.guess_type(pdf_path)
    is_pdf = bool(mt == "application/pdf" or pdf_path.lower().endswith(".pdf"))
    is_image = bool((mt and mt.startswith("image/")) or os.path.splitext(pdf_path)[1].lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".heic", ".heif"})
    if not is_pdf and is_image:
        os.makedirs(output_dir, exist_ok=True)
        temp_pdf = convert_image_to_pdf(pdf_path, output_dir=output_dir)
        work_path = temp_pdf
    raw = call_fortebank_textract(work_path)
    os.makedirs(output_dir, exist_ok=True)
    raw_path = os.path.join(output_dir, "textract_response_raw.json")
    if save_json:
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw)
    # Parse raw JSON safely
    obj = {}
    parse_err = None
    try:
        obj = json.loads(raw)
    except Exception as e:
        parse_err = str(e)
        obj = {}
    # Determine success and error message
    success = bool(obj.get("success")) if isinstance(obj, dict) else False
    error = None
    if not success:
        error = (obj.get("message") or obj.get("error") or parse_err or "Unknown OCR error") if isinstance(obj, dict) else (parse_err or "Unknown OCR error")
    result = {
        "success": success,
        "error": error,
        "raw_path": raw_path,
        "raw_obj": obj if isinstance(obj, dict) else {},
    }
    if temp_pdf and os.path.isfile(temp_pdf):
        try:
            os.remove(temp_pdf)
        except Exception:
            pass
    return result