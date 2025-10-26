import json
import boto3

bedrock = boto3.client("bedrock-runtime")

PROMPT_TEMPLATE = """
You are an expert in multilingual document information extraction and normalization.
Your task is to analyze a noisy OCR text that may contain both Kazakh and Russian fragments.

Follow these steps precisely before producing the final JSON:

STEP 1 — UNDERSTAND THE TASK
You must extract the following information:
- full_name: full name of the person (e.g. **Иванов Иван Иванович**)
- doc_classification: if document matches one of the known templates, classify it as one of:
  - "Лист временной нетрудоспособности (больничный лист)"
  - "Приказ о выходе в декретный отпуск по уходу за ребенком"
  - "Справка о выходе в декретный отпуск по уходу за ребенком"
  - "Выписка из стационара (выписной эпикриз)"
  - "Больничный лист на сопровождающего (если предусмотрено)"
  - "Заключение врачебно-консультативной комиссии (ВКК)"
  - "Справка об инвалидности"
  - "Справка о степени утраты общей трудоспособности"
  - "Приказ/Справка о расторжении трудового договора"
  - "Справка о регистрации в качестве безработного"
  - "Приказ работодателя о предоставлении отпуска без сохранения заработной платы"
  - "Справка о неполучении доходов"
  - "Уведомление о регистрации в качестве лица, ищущего работу"
  - "Лица, зарегистрированные в качестве безработных"
  - null
- doc_date: main issuance date (convert to format DD.MM.YYYY)

STEP 2 — EXTRACTION RULES
- If several dates exist, choose the main *issuance* date (usually near header or "№").
- Ignore duplicates or minor typos.
- When the value is missing, set it strictly to `null`.
- Do not invent or assume missing data.
- If both Russian and Kazakh versions exist, output result in Russian.

STEP 3 — THINK BEFORE ANSWERING
**Double-check**:
- Is full_name complete (Фамилия Имя Отчество)?
- Is doc_date formatted as DD.MM.YYYY?
- Are there exactly 3 keys in the final JSON?
- Is doc_classification one of the allowed options or null?

STEP 4 — OUTPUT STRICTLY IN THIS JSON FORMAT (no explanations, no extra text, no Markdown formatting, and **no ```json** formatting)
{{
  "full_name": string | null,
  "doc_classification": string | null,
  "doc_date": string | null,
}}

Text for analysis:
{}
"""


def lambda_handler(event, context):
    filtered_text = event.get("FilteredTextract") or ""
    if isinstance(filtered_text, dict):
        filtered_text = json.dumps(filtered_text, ensure_ascii=False)

    prompt = PROMPT_TEMPLATE.format(filtered_text)

    payload = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 2000}
    }

    response = bedrock.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        body=json.dumps(payload),
        contentType="application/json",
        accept="application/json"
    )

    body = response["body"]
    if hasattr(body, "read"):
        body = body.read()

    model_raw = json.loads(body)
    output_section = model_raw.get("output", {}).get("message", {}).get("content", [])

    text_output = ""
    for item in output_section:
        text_output += item.get("text", "")

    try:
        extracted = json.loads(text_output)
    except json.JSONDecodeError:
        extracted = {"error": "Invalid JSON output", "raw_text": text_output}

    meta = {
        "ModelId": "amazon.nova-lite-v1:0",
        "StopReason": model_raw.get("stopReason"),
        "Tokens": model_raw.get("usage", {}),
    }

    result = {"ExtractedData": extracted, "Meta": meta}
    return {"statusCode": 200, "modelResponse": result}
