import os
import requests
from typing import Union, Iterable, Dict, Optional,List
from dotenv import load_dotenv
import re
load_dotenv()
class AzureTranslator:
    def __init__(self,
                 api_key: str = os.getenv("MICROSOFT_API_KEY"),
                 endpoint: str = os.getenv("MICROSOFT_ENDPOINT"),
                 region: str = os.getenv("REGION")):
        self.api_key = api_key
        self.endpoint = endpoint
        self.region = region
        self.api_version = "3.0"

        if not all([self.api_key, self.endpoint, self.region]):
            raise ValueError("Thiếu cấu hình API KEY hoặc ENDPOINT hoặc REGION")
    def makeTranscriptText(self,transcriptData, targetLang='vi') -> Optional[str]:
        """
        Ghép toàn bộ transcript thành một đoạn văn duy nhất rồi dịch sang ngôn ngữ đích.
        
        Returns
        -------
        Bản dịch dạng chuỗi, hoặc None nếu lỗi.
        """
        if not transcriptData:
            return None
        # Ghép toàn bộ text lại thành một đoạn
        full_text = " ".join(entry['text'].strip() for entry in transcriptData)
        return full_text
    def mergeTranslatedTextToTranscript(self,transcript, listTextAfterTranslated):
        """
        Gắn kết quả dịch từ listTextAfterTranslated vào từng entry của transcript gốc.

        Args:
            transcript: List[Dict] — các đoạn văn bản gốc [{text, start, duration, ...}]
            listTextAfterTranslated: List[List[str]] — các đoạn văn bản đã dịch (theo chunk)

        Returns:
            List[Dict] — transcript có thêm field `text_vi` là bản dịch.
        """
        merged_transcript = []
        flat_translations = [text for chunk in listTextAfterTranslated for text in chunk]

        if len(flat_translations) != len(transcript):
            raise ValueError("⚠️ Số câu đã dịch không khớp với số câu trong transcript.")

        for i, entry in enumerate(transcript):
            new_entry = entry.copy()
            new_entry['text_vi'] = flat_translations[i]
            merged_transcript.append(new_entry)

        return merged_transcript
        
    def split_transcript(self, entries, max_chars=4500, max_items=100):
        """
        Chia transcript đầu vào thành các chunk,
        mỗi chunk là list các dict gốc: {text, start, duration},
        sao cho tổng độ dài text trong 1 chunk không vượt quá max_chars.
        """
        chunks = []
        current_chunk = []
        current_chunk_len = 0

        for entry in entries:
            sentence = entry['text'].strip()
            sentence_len = len(sentence)

            # Nếu còn chỗ trong chunk hiện tại
            if (current_chunk_len + sentence_len <= max_chars) and (len(current_chunk) < max_items):
                current_chunk.append(entry['text'])
                current_chunk_len += sentence_len + 1
            else:
                # Đóng chunk lại và bắt đầu chunk mới
                chunks.append(current_chunk)
                current_chunk = [entry['text']]
                current_chunk_len = sentence_len + 1

        # Thêm chunk cuối nếu còn
        if current_chunk:
            chunks.append(current_chunk)

        return chunks


    def translate(self,
                texts: Union[str, List[str]],
                source_lang: Optional[str] = "",
                target_langs: Union[str, Iterable[str]] = "vi",
                timeout: int = 10) -> Optional[List[Dict[str, str]]]:
        """
        Dịch một hoặc nhiều đoạn văn bản sang một hoặc nhiều ngôn ngữ.

        Args:
            texts: Chuỗi hoặc danh sách các chuỗi văn bản cần dịch.
            source_lang: Ngôn ngữ gốc (nếu không truyền thì tự động phát hiện).
            target_langs: Một ngôn ngữ hoặc danh sách các ngôn ngữ đích.
            timeout: Thời gian chờ tối đa cho request.

        Returns:
            List[Dict[str, str]]: Danh sách kết quả dịch theo thứ tự đầu vào.
                Mỗi phần tử là dict {lang_code: translated_text}
        """
        # Chuẩn hóa đầu vào
        if isinstance(texts, str):
            texts = [texts]
        if isinstance(target_langs, str):
            target_langs = [target_langs]
        else:
            target_langs = list(target_langs)

        # Tạo query string
        params = [f"api-version={self.api_version}"]
        if source_lang:
            params.append(f"from={source_lang}")
        params.extend([f"to={lang}" for lang in target_langs])
        route = "/translate?" + "&".join(params)

        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Ocp-Apim-Subscription-Region": self.region,
            "Content-Type": "application/json"
        }

        # Body gồm danh sách các object {"Text": ...}
        body = [{"Text": text} for text in texts]

        try:
            response = requests.post(
                url=self.endpoint + route,
                headers=headers,
                json=body,
                timeout=timeout
            )
            response.raise_for_status()
            data = response.json()

            # Trả về list có cùng thứ tự với `texts`
            result = []
            for item in data:
                translations = {t["to"]: t["text"] for t in item["translations"]}
                result.append(translations)

            return result

        except requests.exceptions.RequestException as err:
            print(f"⚠️ Translator API error: {err}")
            return None
