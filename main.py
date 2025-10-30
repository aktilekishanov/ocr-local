from rbidp.clients.gpt_client import ask_gpt
from rbidp.clients.textract_client import ask_textract
from typing import Dict, Any
from rapidfuzz import fuzz
import re
 
def main():
 
    # # Textract (three-line caller)
    # # work pc path: "C:/Users/AIshanov/personal/ds/rb-ocr/ocr-local/ocr-local-main/data/Приказ о выходе в декретный отпуск/3. Приказ о выходе в декретный отпуск.pdf"
    # pdf_path = "C:/Users/AIshanov/personal/ds/rb-ocr/ocr-local/ocr-local-main/data/Приказ о выходе в декретный отпуск/3. Приказ о выходе в декретный отпуск.pdf"
    # text = ask_textract(pdf_path, output_dir="output", save_json=True, save_filtered_json=True)
    # print(text)
   
    # # GPT (three-line caller)
    # prompt = "when is christmas in the states?"
    # response = ask_gpt(prompt)
    # print(response)
 
    # # TEST GPT
    # prompt = """
    # SYSTEM INSTRUCTION:
    # You are a precise document-type classifier. Your goal is to decide if the input OCR text represents ONE distinct document type or multiple.
 
    # TASK:
    # Return strictly a JSON object:
    # {"single_doc_type": boolean}
 
    # DEFINITIONS:
    # - A *document type* = the document’s purpose (e.g., order, certificate, medical form, ID, decree).  
    # - Different languages, duplicated headers, or OCR artifacts do NOT mean multiple documents.  
    # - Only count as multiple if content clearly shows distinct purposes, issuers, people, or form numbers.
 
    # DECISION RULES:
    # 1. Same form number, same organization, same person, same purpose → true.  
    # 2. Repeated headers, bilingual duplicates, or OCR noise → ignore → still true.  
    # 3. Two or more unrelated forms (different document names, people, or cases) → false.  
    # 4. If unclear, but all content aligns with one document → default to true.
 
    # EXAMPLES:
    # - “БҰЙРЫҚ / ПРИКАЗ” bilingual with same signature → true  
    # - “ПРИКАЗ” + “СПРАВКА” → false  
    # - Header repeated due to OCR → true  
    # - Two different signatures for two people → false
 
    # OUTPUT:
    # Respond with only:
    # {"single_doc_type": true}
    # or
    # {"single_doc_type": false}
 
    # INPUT TEXT:
    # {
    #   "pages": [
    #     {
    #       "page_number": 1,
    #       "text": "35,a3aKcTaH Республикась\nпазаястан Республикасы\nДенсаулых caKTay министрлів\nДенсаулык caKTay министрінік M.a 2020жылны «30»\nИннистерство цдравоохранения\nазандары No1 75/2020 буйрыльмен бекітілген N1026/y\nРеспублики Ka3aHcTaH\nнысанды медицинальн, кужаттама\nГиминый атауы\nМедицинская документация\nнаименование организации\nФорма No 026/y утверждена приназом\nTOO CBA Интерление Ансай\nМинистра здравоохранения\nРеспублики Ka3axcTaH\nCT 30 октября 2020 года\nNo (P ДCM-175/2020\nФорма № 026/y\n\"Заключение врачебно - консультационной комиссии\"\n№ 9 01.06.2025Γ\nФ. И.О: Айбулова Эльвира Акбаевна\nДата рождения: 22.11.1987\nПол: жен\nИндивидуальный идентификационный HoMep 871122401427\nДомашний алрес. телефон: PK. 3KO Γ. Аксай\nMecro работы: KIIO бв. специалист\nДиагнозы: Беременность 29 недель.\nЗаключение врачебно- консультативной комиссии: Справка no MecTy требования\nSPAY\nПредседатель комиссии: Касымова P.P\nЧлены комиссии\nУмурзакова БУ\nДОРШЕР\nСеитова Γ.3\nBPALL\nVIID.\n-\nСекрстарь\nМырзалисва A.A\nСейт"
    #     }
    #   ]
    # }
    # """
    # response = ask_gpt(prompt)
    # print(response)
 
    def _norm_text(s: Any) -> str:
        if not isinstance(s, str):
            return ""
        # collapse whitespace and lowercase
        s = re.sub(r"\s+", " ", s.strip())
        return s.casefold()
 
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
 
    fio_meta = "Наурызбаева Нұргүл Мұхитқызы"
    fio = "НАУРЫЗБАЕВА НУРГУЛ МУХИТКЫЗЫ"
 
    fio_meta_norm = _norm_text(kz_to_ru(fio_meta))
    fio_norm = _norm_text(fio)
 
    score = fuzz.token_sort_ratio(fio_meta_norm, fio_norm)
 
    
    print(fio_meta_norm + " vs " + fio_norm )
    print(score)
 
if __name__ == "__main__":
    main()