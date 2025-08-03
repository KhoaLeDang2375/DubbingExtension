import os
import requests
import logging
from dotenv import load_dotenv
import google.generativeai as genai
from typing import Union, Iterable, Dict, Optional,List
import ast
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    VideoUnavailable,
    NoTranscriptFound
)
# Load environment variables từ .env
load_dotenv()

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class GenAITranslator:
    def __init__(self, youtubeAPIKey=None, geminiAPIKey=None,video_id= None):
        # Lấy API Key từ biến môi trường nếu không truyền vào
        if not video_id:
            logging.error("Thiếu video_id.")
            raise ValueError("Phải cung cấp video_id.")
        self.youtubeAPIKey = youtubeAPIKey or os.getenv('YOUTUBE_API_V3')
        self.geminiAPIKey = geminiAPIKey or os.getenv('GOOGLE_API_KEY')
        self.video_id = video_id
        self.metadata = get_youtube_metadata(video_id,self.youtubeAPIKey)
        if not self.metadata:
            logging.error(f"Không tìm thấy metadata cho video_id: {video_id}")
            return []
        # Kiểm tra khóa API
        if not self.youtubeAPIKey or not self.geminiAPIKey:
            raise ValueError("Thiếu API Key. Vui lòng kiểm tra .env")

        # Cấu hình Google Generative AI
        genai.configure(api_key=self.geminiAPIKey)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        logging.info("Khởi tạo thành công GenAITranslator.")
    def translate(self,  texts: Union[str, List[str]],source_lang = "",target_langs='vi',) -> Optional[List[Dict[str, str]]]:
        # Chuẩn hóa đầu vào
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            logging.warning("Transcript chunk rỗng.")
            return []
        try:
            # Lấy metadata từ YouTube
            metadata = self.metadata
            # Tạo prompt dịch
            prompt = makePrompt(metadata['title'], metadata['description'], metadata['tags'], target_langs, texts)
            # Gọi model Gemini
            logging.info(f"Gọi mô hình Gemini để dịch transcript video_id: {self.video_id}")
            response = self.model.generate_content(prompt)
            # Delete Mark down 
            response = extract_json_content(response.text)
            result = ast.literal_eval(response)
            actual_list = result  # Không cần parse lại
            return [{target_langs: item} for item in actual_list]
        except Exception as e:
            logging.exception(f"Lỗi trong quá trình dịch: {e}")
            return []
import re

def extract_json_content(response):
    """
    Trích xuất nội dung JSON từ phản hồi Gemini AI
    
    Args:
        response (str): Phản hồi từ Gemini AI có chứa markdown
        
    Returns:
        str: Chuỗi JSON đã được làm sạch
    """
    # Tìm và trích xuất nội dung trong code block ```json
    pattern = r'```json\s*\n(.*?)\n```'
    match = re.search(pattern, response, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    
    # Nếu không tìm thấy, trả về nguyên bản
    return response.strip()
def makePrompt(video_title: str, video_description: str, video_tags: list, target_langs='vi', texts=[]) -> str:
    chunk_json_array = ',\n  '.join([f'"{chunk}"' for chunk in texts])
    return f"""You are a professional translator and subtitle expert.
        Your task is to translate EACH sentence in the given JSON array **individually and separately** into {target_langs}.

        ## CONTEXT:
        - Video Title: "{video_title}"
        - Description: "{video_description}"
        - Tags: {video_tags}

        ## INPUT (to translate):
        [
        {chunk_json_array}
        ]

        ## REQUIREMENTS:
        1. Translate **each element separately**, preserving order and count (1:1 mapping).
        2. Output MUST be a JSON array with the same number of strings as the input (i.e., {len(texts)}).
        3. DO NOT merge sentences. DO NOT split any sentence.
        4. DO NOT include any additional explanation, commentary, or formatting.
        5. DO NOT change order or content type.

        ## OUTPUT FORMAT:
        - Return ONLY the JSON array of translated strings.
        - No extra text, headers, markdown, or explanations.

        ## EXAMPLE OUTPUT:
        ["Dòng 1 dịch", "Dòng 2 dịch", ..., "Dòng N dịch"]

        STRICTLY FOLLOW this format or your response will be rejected by the system."""


def get_youtube_metadata(video_id: str, api_key: str) -> Dict:
    """
    Lấy metadata (title, description, tags) từ video YouTube.
    """
    url = f"https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet",
        "id": video_id,
        "key": api_key
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if not data["items"]:
            logging.warning(f"Không tìm thấy video với ID: {video_id}")
            return None

        snippet = data["items"][0]["snippet"]
        return {
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "tags": snippet.get("tags", [])
        }
    except requests.RequestException as req_err:
        logging.error(f"Lỗi khi gọi YouTube API: {req_err}")
        return None
