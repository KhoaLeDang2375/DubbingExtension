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
from Text_To_Speech.TextToSpeech import TextToSpeechModule

from loguru import logger  # Dùng loguru để log thay vì print()

# ------------------ Cấu hình ------------------

app = FastAPI()
translator = AzureTranslator()
tts = TextToSpeechModule()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ Mô hình dữ liệu ------------------

class VideoRequest(BaseModel):
    video_id: str
    target_language: str = "vi"

# ------------------ Hàm phụ trợ ------------------

def get_transcript(data: VideoRequest) -> Dict:
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(data.video_id)
        logger.info(f"📋 Transcript list: {[t.language_code for t in transcript_list]}")

        if data.target_language in [t.language_code for t in transcript_list]:
            transcript = YouTubeTranscriptApi.get_transcript(data.video_id, languages=[data.target_language])
            logger.info(f" Found transcript in target language: {data.target_language}")
            return {"transcript": transcript, "flagTargetLang": True}
        else:
            transcript = YouTubeTranscriptApi.get_transcript(data.video_id)
            logger.warning(" Transcript không có ngôn ngữ đích, dùng bản gốc.")
            return {"transcript": transcript, "flagTargetLang": False}

    except TranscriptsDisabled:
        logger.error(" Transcript bị vô hiệu hóa.")
        raise HTTPException(status_code=403, detail="Transcript is disabled for this video.")
    except VideoUnavailable:
        logger.error("Video không khả dụng.")
        raise HTTPException(status_code=404, detail="Video is unavailable.")
    except NoTranscriptFound:
        logger.error(" Không tìm thấy transcript.")
        raise HTTPException(status_code=404, detail="No transcript found for this video.")
    except Exception as e:
        logger.exception(" Lỗi không xác định khi lấy transcript.")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


def make_caption(transcript: List[Dict]) -> List[Dict]:
    try:
        chunks = translator.split_transcript(transcript)
        translated_chunks = [translator.translate(chunk) for chunk in chunks]
        logger.info(" Đã dịch xong toàn bộ transcript.")
        return translator.mergeTranslatedTextToTranscript(transcript, translated_chunks)
    except Exception as e:
        logger.exception(" Lỗi khi dịch transcript.")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


def build_tts_segments(transcript: List[Dict], language: str = "vi") -> List[Dict]:
    """
    Xây dựng danh sách segment cho TTS.
    - Nếu transcript có 'text_vi' thì sử dụng text_vi[language]
    - Nếu không thì dùng trực tiếp trường 'text' (coi như transcript đã là ngôn ngữ đích)
    """
    segments = []

    for entry in transcript:
        # Nếu có bản dịch thì lấy bản dịch
        if "text_vi" in entry and language in entry["text_vi"]:
            text = entry["text_vi"][language]
        # Nếu không có thì dùng text gốc
        elif "text" in entry:
            text = entry["text"]
        else:
            raise ValueError(f"Không tìm thấy nội dung cho đoạn transcript: {entry}")

        segments.append({
            "text": text,
            "duration": entry["duration"]
        })

    return segments


# ------------------ Endpoint chính ------------------

@app.post("/dubbing")
async def dubbing(data: VideoRequest):
    try:
        logger.info(f" Nhận yêu cầu lồng tiếng video: {data.video_id}")
        transcript_info = get_transcript(data)

        if not transcript_info['flagTargetLang']:
            translated_transcript = make_caption(transcript_info['transcript'])
        else:
            translated_transcript = transcript_info['transcript']

        segments = build_tts_segments(translated_transcript, language=data.target_language)
        ssml = tts.generate_ssml(segments)

        try:
            tts.synthesize_to_file(ssml, "output.mp3")
            logger.info(" Đã phát âm thanh thành công.")
            return {"status": "success", "message": "Đã phát âm thanh thành công!"}
        except Exception as e:
            logger.warning(" Không thể phát trực tiếp. Đang lưu vào file...")
            tts.synthesize_to_file(ssml, "output.mp3")
            return FileResponse("output.mp3", media_type="audio/mpeg", filename="voiceover.mp3")

    except Exception as e:
        logger.exception(" Lỗi xảy ra trong quá trình xử lý dubbing.")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)}
        )
