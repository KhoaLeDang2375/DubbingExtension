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
