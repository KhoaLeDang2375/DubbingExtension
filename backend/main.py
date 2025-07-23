import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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
from redis_cache.cache import multiprocessingForTTSAndTranslator
# ------------------ Cấu hình ứng dụng ------------------

app = FastAPI()
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
# ------------------ Endpoint chính ------------------

@app.post("/dubbing")
async def dubbing(data: VideoRequest):
    logger.info(f"🎬 Nhận yêu cầu lồng tiếng video ID: {data.video_id}")
    translator = get_translator(data.translator, video_id=data.video_id)

    transcript_info = get_transcript(data)
    chunks = transcriptHandler.split_transcript(transcript_info['transcript'], data.video_id)
    logger.info(f"📤 Đã chia transcript thành {len(chunks)} đoạn.")

    if not transcript_info['flagTargetLang']:
        redis_config = {"host": "172.21.106.92", "port": 6379, "db": 0}
        multiprocessingRes = multiprocessingForTTSAndTranslator(
            transcript_chunks=chunks,
            translator_func=translator.translate,
            video_id=data.video_id,
            redis_config=redis_config
        )
        # Lấy danh sách BytesIO
        audio_bytesio_list = multiprocessingRes['ListBytesIO']
        # Trả về chunk đầu tiên (hoặc bạn có thể trả về chunk theo index)
        if audio_bytesio_list and len(audio_bytesio_list) > 0:
            audio_bytesio_list[0].seek(0)
            return StreamingResponse(audio_bytesio_list[0], media_type="audio/mpeg")
        else:
            raise HTTPException(status_code=404, detail="No audio found")
    else:
        segments = transcript_info['transcript']
        logger.info("📌 Sử dụng transcript đã có ngôn ngữ đích, không cần dịch.")
        try:
            tts = TextToSpeechModule()
            logger.info(f"🔊 Đang tạo SSML cho {len(segments)} đoạn.")
            ssml = tts.generate_ssml(segments)
            logger.info(f"📝 SSML đã được tạo:\n{ssml[:500]}...")  # Log 500 ký tự đầu
            audio_bytesio = tts.ssml_to_bytesio(ssml)
            audio_bytesio.seek(0)
            return StreamingResponse(audio_bytesio, media_type="audio/mpeg")
        except Exception as e:
            logger.exception(f"❌ Lỗi khi synthesize TTS: {e}")
            raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {str(e)}")