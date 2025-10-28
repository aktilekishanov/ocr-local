import urllib.request
import ssl
import mimetypes
import os
import uuid
import json
from rbidp.processors.filter_textract_response import filter_textract_response
 
def call_fortebank_textract(pdf_path: str, ocr_engine: str = "textract") -> str:
    """
    Sends a PDF to ForteBank Textract OCR endpoint and returns the raw response.
    """
    url = "http://dev-ocr.fortebank.com/v1/pdf"
 
    # Read file bytes
    with open(pdf_path, "rb") as f:
        file_data = f.read()
 
    # Prepare multipart/form-data body manually
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    content_type = f"multipart/form-data; boundary={boundary}"
 
    filename = os.path.basename(pdf_path)
    mime_type = mimetypes.guess_type(filename)[0] or "application/pdf"
 
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

def ask_textract(pdf_path: str, output_dir: str = "output", save_json: bool = True, save_text: bool = True) -> str:
    raw = call_fortebank_textract(pdf_path)
    os.makedirs(output_dir, exist_ok=True)
    if save_json:
        with open(os.path.join(output_dir, "textract_response_raw.json"), "w", encoding="utf-8") as f:
            f.write(raw)
    obj = json.loads(raw)
    # Save pages JSON via centralized helper and return its path
    try:
        pages_path = filter_textract_response(obj, output_dir, filename="textract_response_filtered.json")
    except Exception:
        pages_path = ""
    return pages_path