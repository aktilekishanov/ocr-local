from gpt_client import ask_gpt
from textract_client import ask_textract
 
def main():

    # Textract (three-line caller)
    # work pc path: "C:/Users/AIshanov/personal/ds/rb-ocr/ocr-local/ocr-local-main/data/Приказ о выходе в декретный отпуск/3. Приказ о выходе в декретный отпуск.pdf"
    pdf_path = "C:/Users/AIshanov/personal/ds/First Working Prototype_v2/ocr/data/Приказ о выходе в декретный отпуск/4. Приказ о выходе в декретный отпуск.pdf"
    text = ask_textract(pdf_path, output_dir="output", save_json=True, save_text=True)
    print(text)
    
    # GPT (three-line caller)
    prompt = "when is christmas in the states?"
    response = ask_gpt(prompt)
    print(response)

 
if __name__ == "__main__":
    main()