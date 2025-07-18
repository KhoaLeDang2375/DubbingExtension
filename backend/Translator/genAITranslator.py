import os
import requests
import logging
from typing import List, Dict
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables từ .env
load_dotenv()

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class GenAITranslator:
    def __init__(self, youtubeAPIKey=None, geminiAPIKey=None):
        # Lấy API Key từ biến môi trường nếu không truyền vào
        self.youtubeAPIKey = youtubeAPIKey or os.getenv('YOUTUBE_API_V3')
        self.geminiAPIKey = geminiAPIKey or os.getenv('GOOGLE_API_KEY')

        # Kiểm tra khóa API
        if not self.youtubeAPIKey or not self.geminiAPIKey:
            raise ValueError("Thiếu API Key. Vui lòng kiểm tra .env")

        # Cấu hình Google Generative AI
        genai.configure(api_key=self.geminiAPIKey)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        logging.info("Khởi tạo thành công GenAITranslator.")
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
    def translate(self, target_language='vi', transcript_chunk: List[Dict] = [], video_id: str = '') -> List[str]:
        if not video_id:
            logging.error("Thiếu video_id.")
            raise ValueError("Phải cung cấp video_id.")

        if not transcript_chunk:
            logging.warning("Transcript chunk rỗng.")
            return []

        try:
            # Lấy metadata từ YouTube
            metadata = get_youtube_metadata(video_id=video_id, api_key=self.youtubeAPIKey)
            if not metadata:
                logging.error(f"Không tìm thấy metadata cho video_id: {video_id}")
                return []

            # Tạo prompt dịch
            prompt = makePrompt(metadata['title'], metadata['description'], metadata['tags'], target_language, transcript_chunk)

            # Gọi model Gemini
            logging.info(f"Gọi mô hình Gemini để dịch transcript video_id: {video_id}")
            response = self.model.generate_content(prompt)

            if hasattr(response, 'text'):
                # Giả định kết quả là một list string JSON
                try:
                    import json
                    result = json.loads(response.text)
                    if isinstance(result, list):
                        logging.info("Dịch thành công.")
                        return result
                    else:
                        logging.error("Kết quả không phải danh sách.")
                        return []
                except Exception as parse_err:
                    logging.error(f"Lỗi phân tích kết quả dịch: {parse_err}")
                    return []
            else:
                logging.error("Không có thuộc tính 'text' trong response Gemini.")
                return []

        except Exception as e:
            logging.exception(f"Lỗi trong quá trình dịch: {e}")
            return []

def makePrompt(video_title: str, video_description: str, video_tags: list, target_language='vi', transcript_chunk=[]) -> str:
    """
    Tạo prompt để gửi đến Gemini nhằm dịch transcript theo ngữ cảnh.
    """
    return f"""
        You are a professional translator and subtitle expert.
        Your task is to translate short transcript segments from a video to the target language in a way that preserves the meaning, tone, and clarity, while ensuring synchronization with voice-over and subtitle use.
        
        ## Input:
        - Title: "{video_title}"
        - Description: "{video_description}"
        - Tags: {video_tags}
        - Target Language: {target_language}
        - Transcript Chunk (source language will be automatically detected):
        {transcript_chunk}

        ## Requirements:
        1. Detect the source language automatically and translate it to the specified target language.
        2. Translate *only* the `text` content in each item.
        3. Output should be a list of translated strings in the **same order**, **without adding extra commentary, metadata or numbering**.
        4. Keep sentence structure natural in the target language but do **not add information not present** in the original.
        5. Use metadata (title, description, tags) **only to infer context** or ambiguous terms, *not to expand or reinterpret* the transcript.
        6. Avoid hallucination — keep translations tight and aligned with original meaning.
        7. Each translated sentence must match roughly in **length and tone** to be suitable for dubbing.

        ## Output Format:
        A list of translated strings, same length and order as input. Example:
        ["...", "...", "..."]
    """

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
