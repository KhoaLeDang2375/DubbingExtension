import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    VideoUnavailable,
    NoTranscriptFound
)
from pydantic import BaseModel
from typing import List, Dict

from Translator.translator import AzureTranslator
from Translator.genAITranslator import GenAITranslator
from Text_To_Speech.TextToSpeech import TextToSpeechModule
from Handler_Transcript.Handler_Transcript import Handler
from loguru import logger

# ------------------ Cấu hình ứng dụng ------------------

app = FastAPI()
tts = TextToSpeechModule()
transcriptHandler = Handler()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ Mapping Translator ------------------

TRANSLATOR_MAP = {
    "AzureTranslator": AzureTranslator,
    "GenAITranslator": GenAITranslator
}

def get_translator(name: str, video_id: str = None):
    """
    Factory method: khởi tạo translator theo tên, truyền video_id nếu cần.
    """
    cls = TRANSLATOR_MAP.get(name)
    if not cls:
        logger.error(f"❌ Translator không được hỗ trợ: {name}")
        raise HTTPException(status_code=400, detail=f"Unsupported translator: {name}")
    logger.info(f"✅ Sử dụng translator: {name}")

    # Nếu translator yêu cầu video_id (như GenAI)
    if name == "GenAITranslator":
        return cls(video_id=video_id)
    return cls()

# ------------------ Schema ------------------

class VideoRequest(BaseModel):
    video_id: str
    target_language: str = "vi"
    translator: str = "AzureTranslator"

# ------------------ Hàm xử lý phụ trợ ------------------

def get_transcript(data: VideoRequest) -> Dict:
    """
    Trả về transcript gốc hoặc đã có ngôn ngữ đích.
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(data.video_id)
        logger.info(f"📋 Danh sách transcript: {[t.language_code for t in transcript_list]}")

        if data.target_language in [t.language_code for t in transcript_list]:
            transcript = YouTubeTranscriptApi.get_transcript(data.video_id, languages=[data.target_language])
            logger.info(f"✅ Đã tìm thấy transcript ngôn ngữ đích: {data.target_language}")
            return {"transcript": transcript, "flagTargetLang": True}
        else:
            transcript = YouTubeTranscriptApi.get_transcript(data.video_id)
            logger.warning("⚠️ Không có transcript đích, sử dụng transcript gốc.")
            return {"transcript": transcript, "flagTargetLang": False}

    except TranscriptsDisabled:
        logger.error("🚫 Transcript đã bị tắt.")
        raise HTTPException(status_code=403, detail="Transcript is disabled for this video.")
    except VideoUnavailable:
        logger.error("🚫 Video không khả dụng.")
        raise HTTPException(status_code=404, detail="Video is unavailable.")
    except NoTranscriptFound:
        logger.error("🚫 Không tìm thấy transcript.")
        raise HTTPException(status_code=404, detail="No transcript found for this video.")
    except Exception as e:
        logger.exception("❌ Lỗi không xác định khi lấy transcript.")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

def make_caption(transcript: List[Dict], translator, video_id: str = None) -> List[Dict]:
    """
    Dịch transcript sang ngôn ngữ đích. Truyền video_id nếu translator cần.
    """
    try:
        chunks = transcriptHandler.split_transcript(transcript)
        logger.info(f"📤 Đã chia transcript thành {len(chunks)} đoạn.")
        translated_chunks = [translator.translate(chunk) for chunk in chunks]
        logger.info("✅ Đã dịch xong toàn bộ transcript.")
        return transcriptHandler.mergeTranslatedTextToTranscript(transcript, translated_chunks)

    except Exception as e:
        logger.exception("❌ Lỗi khi dịch transcript.")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

def build_tts_segments(transcript: List[Dict], language: str = "vi") -> List[Dict]:
    """
    Chuẩn bị dữ liệu để tổng hợp giọng nói.
    """
    segments = []
    for entry in transcript:
        if "text_vi" in entry and language in entry["text_vi"]:
            text = entry["text_vi"][language]
        elif "text" in entry:
            text = entry["text"]
        else:
            raise ValueError(f"❌ Không có nội dung hợp lệ trong đoạn transcript: {entry}")
        segments.append({
            "text": text,
            "duration": entry["duration"]
        })

    logger.info(f"📦 Đã xây dựng {len(segments)} đoạn âm thanh cho TTS.")
    return segments

# ------------------ Endpoint chính ------------------

@app.post("/dubbing")
async def dubbing(data: VideoRequest):
    logger.info(f"🎬 Nhận yêu cầu lồng tiếng video ID: {data.video_id}")
    translator = get_translator(data.translator, video_id=data.video_id)

    transcript_info = get_transcript(data)

    if not transcript_info['flagTargetLang']:
        translated_transcript = make_caption(
            transcript=transcript_info['transcript'],
            translator=translator,
            video_id=data.video_id
        )
    else:
        translated_transcript = transcript_info['transcript']
        logger.info("📌 Sử dụng transcript đã có ngôn ngữ đích, không cần dịch.")

    return translated_transcript