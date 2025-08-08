import os
from fastapi.responses import JSONResponse
import base64

import json
import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    VideoUnavailable,
    NoTranscriptFound
)
from pydantic import BaseModel, Field
from typing import List, Dict
from Translator.translator import AzureTranslator
from Translator.genAITranslator import GenAITranslator
from Text_To_Speech.TextToSpeech import TextToSpeechModule
from Handler_Transcript.Handler_Transcript import Handler
from loguru import logger
from redis_cache.cache import multiprocessingForTTSAndTranslator, push_all_chunks_to_redis

# ------------------ Cấu hình ứng dụng ------------------

app = FastAPI()
transcriptHandler = Handler()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ Mapping Translator ------------------

TRANSLATOR_MAP = {
    "AzureTranslator": AzureTranslator,
    "GenAITranslator": GenAITranslator
}

def get_translator(name: str, video_id: str = None):
    cls = TRANSLATOR_MAP.get(name)
    if not cls:
        logger.error(f"❌ Translator không được hỗ trợ: {name}")
        raise HTTPException(status_code=400, detail=f"Unsupported translator: {name}")
    logger.info(f"✅ Sử dụng translator: {name}")
    return cls(video_id=video_id) if name == "GenAITranslator" else cls()


# ------------------ Schema ------------------

class DubbingRequest(BaseModel):
    video_id: str
    list_chunks_id: List[str]
    source_lang: str = ""
    target_language: str = "vi"
    translator: str = "AzureTranslator"
    tts_voice: str = Field(..., description="Tên giọng đọc TTS")
    need_translator: bool

class VideoRequest(BaseModel):
    video_id: str
    target_language: str = "vi"

# ------------------ Hàm xử lý phụ trợ ------------------

def get_transcript(data: VideoRequest) -> Dict:
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

# ------------------ Endpoint ------------------

@app.post("/video_split")
async def split(data: VideoRequest):
    logger.info(f"🎬 Nhận yêu cầu lồng tiếng video ID: {data.video_id}")
    transcript_info = get_transcript(data)
    chunks = transcriptHandler.split_transcript(transcript_info['transcript'], data.video_id)
    
    redis_config = {"host": "172.21.106.92", "port": 6379, "db": 0}
    push_all_chunks_to_redis(chunks=chunks, redis_config=redis_config)
    
    logger.info(f"📤 Đã chia transcript thành {len(chunks)} đoạn.")
    list_chunks_id = [item['id'] for item in chunks]
    
    return {
        'total': len(list_chunks_id),
        'info' : transcript_info,
        'list_chunks': [
                        item.split('_')[1]
                        for item in list_chunks_id
                        if '_' in item and len(item.split('_')) > 1
                    ],
        'need_translator': not transcript_info['flagTargetLang']
    }

@app.post("/dubbing")
async def dubbing(data: DubbingRequest):
    redis_config = {"host": "172.21.106.92", "port": 6379, "db": 0}

    if data.need_translator:
        translator = get_translator(data.translator, video_id=data.video_id)
        multiprocessing_res = multiprocessingForTTSAndTranslator(
            list_chunk_ids=data.list_chunks_id,
            translator_func=translator.translate,
            source_lang=data.source_lang,
            target_lang=data.target_language,
            video_id=data.video_id,
            tts_voice=data.tts_voice,
            redis_config=redis_config
        )

        audio_chunks = multiprocessing_res['audio_chunks']

        if audio_chunks:
            result = []
            for item in audio_chunks:
                item["audio_bytesio"].seek(0)
                audio_base64 = base64.b64encode(item["audio_bytesio"].read()).decode('utf-8')
                result.append({
                    "chunk_id": item["chunk_id"],
                    "audio_base64": audio_base64,
                })

            return JSONResponse(content={"chunks": result})

        raise HTTPException(status_code=404, detail="No audio found")

    
    else:
        redis_conn = redis.Redis(**redis_config)
        segments = []

        for chunk_id in data.list_chunks_id:
            raw_chunk = redis_conn.get(f"transcript:{chunk_id}")
            if raw_chunk:
                try:
                    chunk_data = json.loads(raw_chunk)
                    segments.append(chunk_data)
                except Exception as e:
                    logger.warning(f"❌ Lỗi decode chunk {chunk_id}: {e}")
            else:
                logger.warning(f"[TTS] Không tìm thấy chunk: {chunk_id}")

        if not segments:
            raise HTTPException(status_code=404, detail="Không có transcript hợp lệ")

        try:
            tts = TextToSpeechModule(voice=data.tts_voice, output_format="webm")
            logger.info(f"🔊 Đang tạo SSML cho {len(segments)} đoạn.")
            ssml = tts.generate_ssml(segments)
            logger.info(f"📝 SSML đã được tạo:\n{ssml[:500]}...")
            audio_bytesio = tts.ssml_to_bytesio(ssml)
            audio_bytesio.seek(0)
            # Trả về một danh sách chứa một BytesIO được mã hóa
            audio_base64 = base64.b64encode(audio_bytesio.read()).decode('utf-8')
            return JSONResponse(content={
                "chunks": [{"chunk_id": "combined", "audio_base64": audio_base64}]
            })
        except Exception as e:
            logger.exception(f"❌ Lỗi khi synthesize TTS: {e}")
            raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {str(e)}")