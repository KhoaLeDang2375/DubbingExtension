from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    VideoUnavailable,
    NoTranscriptFound
)
from pydantic import BaseModel
from typing import Optional
from Translator.translator import AzureTranslator
translator = AzureTranslator()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
#------------------------------------------------ Request Model ----------------------------------------------
class VideoRequest(BaseModel):
    video_id: str
    target_langugue: str = "en"

#------------------------------------------------ Response Model ----------------------------------------------


#------------------------------------------------ Function ----------------------------------------------

    

@app.post("/get-transcript")
async def get_transcript(data: VideoRequest):
    try:
        # Lấy danh sách transcript có sẵn
        transcript_list = YouTubeTranscriptApi.list_transcripts(data.video_id)

        # Kiểm tra có transcript cho ngôn ngữ đích không
        if data.target_langugue not in [t.language_code for t in transcript_list]:
            transcript = YouTubeTranscriptApi.get_transcript(data.video_id)
            textForTranslate = translator.makeTranscriptText(transcript)
            transcriptAfterTransalted = translator.translate(textForTranslate,data.target_langugue)
            return {"textAfterTranslated": transcriptAfterTransalted[data.target_langugue]}
        else:
            # Nếu có, lấy transcript theo ngôn ngữ đích
            transcript = YouTubeTranscriptApi.get_transcript(
                data.video_id,
                languages=[data.target_langugue]
            )
            chunksForTranslate = translator.split_transcript(transcript)
            chunkAfterTranslated = []
            for chunk in chunksForTranslate:
                listTextTranslated = translator.translate(chunk)
                chunkAfterTranslated.append(listTextTranslated)
            return translator.mergeTranslatedTextToTranscript(transcript,chunkAfterTranslated)

    except TranscriptsDisabled:
        raise HTTPException(status_code=403, detail="Transcript is disabled for this video.")
    except VideoUnavailable:
        raise HTTPException(status_code=404, detail="Video is unavailable.")
    except NoTranscriptFound:
        raise HTTPException(status_code=404, detail="No transcript found for this video.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
