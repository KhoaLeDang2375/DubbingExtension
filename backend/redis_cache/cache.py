import multiprocessing
import redis
from io import BytesIO
from loguru import logger
from Handler_Transcript.Handler_Transcript import Handler
from fastapi import HTTPException
from Text_To_Speech.TextToSpeech import TextToSpeechModule
from typing import List, Dict
import json

def translate_chunk(chunk: Dict, translator_func, handler, video_id) -> List[Dict]:
    """
    Dịch transcript sang ngôn ngữ đích. Truyền video_id nếu translator cần.
    """
    try:
        entries = chunk["chunk"]
        texts = [entry["text"] for entry in entries]
        logger.info("Hoàn thành lấy dữ liệu text trong các chunk")
        rawTextAfterTranslate = translator_func(texts)
        return handler.merge_chunk_translation(chunk=entries, translated_result=rawTextAfterTranslate)
    except Exception as e:
        logger.exception("❌ Lỗi khi dịch transcript.")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

def translator_process(transcript_chunks, translator_func, video_id, redis_config):
    redis_conn = redis.Redis(**redis_config)
    handler = Handler()
    for idx, chunk in enumerate(transcript_chunks):
        try:
            merged = translate_chunk(chunk, translator_func, handler, video_id)
            chunk_id = f"{chunk['id']}_{video_id}"
            # Thêm TTL 1 giờ (3600 giây) cho translation
            redis_conn.set(f"translation:{chunk_id}", json.dumps(merged, ensure_ascii=False), ex=3600)
            redis_conn.publish("translation_ready", chunk_id)
            logger.info(f"[Translator] Done: {chunk_id}")
        except Exception as e:
            logger.error(f"[Translator] Failed on chunk {chunk}: {e}")

def tts_process(video_id, redis_config):
    redis_conn = redis.Redis(**redis_config)
    tts = TextToSpeechModule()
    handler = Handler()
    pubsub = redis_conn.pubsub()
    pubsub.subscribe("translation_ready")
    for message in pubsub.listen():
        if message['type'] != 'message':
            continue
        chunk_id = message['data'].decode("utf-8")
        try:
            translated = redis_conn.get(f"translation:{chunk_id}")
            if not translated:
                logger.error(f"[TTS] No translation for {chunk_id}")
                continue
            merged_chunk = json.loads(translated)
            ssml = tts.generate_ssml(merged_chunk)
            audio_bytesio = tts.ssml_to_bytesio(ssml)
            # Thêm TTL 1 giờ (3600 giây) cho audio
            redis_conn.set(f"audio:{chunk_id}", audio_bytesio.getvalue(), ex=3600)
            logger.info(f"[TTS] Done: {chunk_id}")
        except Exception as e:
            logger.error(f"[TTS] Error on chunk {chunk_id}: {e}")

def collect_audio_bytesio(transcript, video_id, redis_config):
    """
    Thu thập các audio bytesIO từ Redis cho từng chunk, trả về list BytesIO.
    """
    redis_conn = redis.Redis(**redis_config)
    audio_bytesio_list = []
    for idx in range(len(transcript)):
        chunk_id = f"{transcript[idx]['id']}_{video_id}"
        audio_bytes = redis_conn.get(f"audio:{chunk_id}")
        if audio_bytes:
            audio_bytesio_list.append(BytesIO(audio_bytes))
        else:
            logger.warning(f"❌ No audio for {chunk_id}")
    return audio_bytesio_list

def collect_merged_chunks_from_redis(transcript_chunks, video_id, redis_config):
    """
    Lấy danh sách các merged chunk đã dịch từ Redis để làm đầu vào cho mergeTranslatedTextToTranscript.
    Trả về: List[List[Dict]] (mỗi phần tử là 1 chunk đã merge)
    """
    redis_conn = redis.Redis(**redis_config)
    merged_chunks = []
    for chunk in transcript_chunks:
        chunk_id = f"{chunk['id']}_{video_id}"
        merged_bytes = redis_conn.get(f"translation:{chunk_id}")
        if merged_bytes:
            try:
                merged_chunk = json.loads(merged_bytes)
                merged_chunks.append(merged_chunk)
            except Exception as e:
                logger.error(f"Lỗi khi decode merged chunk {chunk_id}: {e}")
        else:
            logger.warning(f"Không tìm thấy merged chunk cho {chunk_id}")
    return merged_chunks

def multiprocessingForTTSAndTranslator(transcript_chunks, translator_func, video_id, redis_config):
    translator = multiprocessing.Process(
        target=translator_process, args=(transcript_chunks, translator_func, video_id, redis_config)
    )
    tts = multiprocessing.Process(
        target=tts_process, args=(video_id, redis_config)
    )

    translator.start()
    tts.start()

    translator.join()
    tts.terminate()

    print("\n🎉 All tasks completed.\n")
    # Log kết quả Redis
    redis_conn = redis.Redis(**redis_config)
    for idx in range(len(transcript_chunks)):
        chunk_id = f"{transcript_chunks[idx]['id']}_{video_id}"
        audio = redis_conn.get(f"audio:{chunk_id}")
        print(f"{chunk_id} -> Audio Bytes Length: {len(audio) if audio else '❌ No audio'}")
    return {"transcriptAfterTranslated":collect_merged_chunks_from_redis(transcript_chunks, video_id, redis_config),"ListBytesIO":collect_audio_bytesio(transcript_chunks,video_id,redis_config)}