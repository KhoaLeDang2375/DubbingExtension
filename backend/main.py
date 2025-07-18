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

from loguru import logger  # Dùng loguru để log thay vì print()

# ------------------ Cấu hình ứng dụng ------------------

app = FastAPI()
tts = TextToSpeechModule()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ Chọn Translator ------------------

# Mapping giữa tên và class
TRANSLATOR_MAP = {
    "AzureTranslator": AzureTranslator,
    "GenAITranslator": GenAITranslator
}

def get_translator(name: str):
    """
    Factory method để lấy đúng class translator từ tên.
    """
    cls = TRANSLATOR_MAP.get(name)
    if not cls:
        logger.error(f"❌ Translator không được hỗ trợ: {name}")
        raise HTTPException(status_code=400, detail=f"Unsupported translator: {name}")
    logger.info(f"✅ Sử dụng translator: {name}")
    return cls()

# ------------------ Mô hình dữ liệu ------------------

class VideoRequest(BaseModel):
    video_id: str
    target_language: str = "vi"
    translator: str = "AzureTranslator"  # Có thể là "AzureTranslator" hoặc "GenAITranslator"

# ------------------ Hàm phụ trợ ------------------

def get_transcript(data: VideoRequest) -> Dict:
    """
    Trả về transcript gốc hoặc transcript đã có ngôn ngữ đích.
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(data.video_id)
        logger.info(f"📋 Danh sách transcript: {[t.language_code for t in transcript_list]}")

        # Nếu đã có bản transcript đúng target_language thì dùng luôn
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
    Dịch transcript sang ngôn ngữ đích bằng translator được chọn.
    Nếu translator hỗ trợ xử lý theo video_id (ví dụ Gemini), truyền thêm tham số này.
    """
    try:
        # Bước 1: Chia nhỏ transcript thành các đoạn chunks
        chunks = translator.split_transcript(transcript)
        logger.info(f"📤 Đã chia transcript thành {len(chunks)} đoạn.")

        # Bước 2: Dịch từng chunk, có thể kèm theo video_id nếu cần
        translated_chunks = []
        for chunk in chunks:
            # Nếu translator hỗ trợ translate(chunk, video_id=...)
            try:
                translated = translator.translate(transcript_chunk=chunk, video_id=video_id)
            except TypeError:
                # fallback cho các translator không dùng video_id
                translated = translator.translate(chunk)
            translated_chunks.append(translated)

        logger.info("✅ Đã dịch xong toàn bộ transcript.")

        # Bước 3: Gộp kết quả dịch lại vào transcript gốc
        return translator.mergeTranslatedTextToTranscript(transcript, translated_chunks)

    except Exception as e:
        logger.exception("❌ Lỗi khi dịch transcript.")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


def build_tts_segments(transcript: List[Dict], language: str = "vi") -> List[Dict]:
    """
    Chuyển transcript đã dịch thành segment cho Text-to-Speech.
    Ưu tiên sử dụng bản dịch nếu có.
    """
    segments = []
    for entry in transcript:
        # Ưu tiên dùng bản dịch nếu có
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
    # try:
        logger.info(f"🎬 Nhận yêu cầu lồng tiếng video ID: {data.video_id}")
        translator = get_translator(data.translator)

        # Bước 1: Lấy transcript từ video
        transcript_info = get_transcript(data)

        # Bước 2: Dịch nếu chưa có bản transcript ngôn ngữ đích
        if not transcript_info['flagTargetLang']:
            translated_transcript = make_caption(transcript_info['transcript'], translator,data.video_id)
        else:
            translated_transcript = transcript_info['transcript']
            logger.info("📌 Sử dụng transcript đã có ngôn ngữ đích, không cần dịch.")
        return translated_transcript
    #     # Bước 3: Chuẩn bị cho TTS
    #     segments = build_tts_segments(translated_transcript, language=data.target_language)
    #     ssml = tts.generate_ssml(segments)

    #     # Bước 4: Tổng hợp thành file mp3
    #     try:
    #         tts.synthesize_to_file(ssml, "output.mp3")
    #         logger.info("✅ Đã tổng hợp giọng nói thành công.")
    #         return {"status": "success", "message": "Đã phát âm thanh thành công!"}
    #     except Exception as e:
    #         logger.warning("⚠️ Không thể phát trực tiếp. Lưu file thay thế...")
    #         tts.synthesize_to_file(ssml, "output.mp3")
    #         return FileResponse("output.mp3", media_type="audio/mpeg", filename="voiceover.mp3")

    # except Exception as e:
    #     logger.exception("❌ Lỗi xảy ra trong quá trình xử lý dubbing.")
    #     return JSONResponse(
    #         status_code=500,
    #         content={"status": "error", "detail": str(e)}
    #     )
