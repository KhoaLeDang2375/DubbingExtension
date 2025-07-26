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
    try:
        entries = chunk["chunk"]
        texts = [entry["text"] for entry in entries]
        logger.info("📘 [Translator] Đang dịch chunk...")
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
            chunk_id = f"{chunk['id']}"
            merged = translate_chunk(chunk, translator_func, handler, video_id)
            redis_conn.set(f"translation:{chunk_id}", json.dumps(merged, ensure_ascii=False), ex=3600)
            redis_conn.lpush("translation_queue", chunk_id)
            logger.info(f"✅ [Translator] Hoàn tất chunk: {chunk_id}")
        except Exception as e:
            logger.error(f"❌ [Translator] Lỗi chunk {chunk['id']}: {e}")

def tts_process(redis_config, total_chunks):
    redis_conn = redis.Redis(**redis_config)
    tts = TextToSpeechModule()

    logger.info("📗 [TTS] Bắt đầu lắng nghe queue...")

    processed_chunks = 0
    processed_set = set()

    while processed_chunks < total_chunks:
        result = redis_conn.brpop("translation_queue", timeout=10)
        if result is None:
            logger.warning("[TTS] Timeout khi chờ dữ liệu mới...")
            continue

        _, chunk_id = result
        chunk_id = chunk_id.decode("utf-8")

        if chunk_id in processed_set:
            logger.warning(f"[TTS] Chunk {chunk_id} đã xử lý, bỏ qua.")
            continue

        try:
            translated = redis_conn.get(f"translation:{chunk_id}")
            if not translated:
                logger.error(f"[TTS] Không tìm thấy bản dịch cho {chunk_id}")
                continue

            merged_chunk = json.loads(translated)
            ssml = tts.generate_ssml(merged_chunk)
            audio_bytesio = tts.ssml_to_bytesio(ssml)
            redis_conn.set(f"audio:{chunk_id}", audio_bytesio.getvalue(), ex=3600)

            logger.info(f"✅ [TTS] Đã xử lý xong chunk: {chunk_id}")

            processed_chunks += 1
            processed_set.add(chunk_id)

        except Exception as e:
            logger.error(f"[TTS] Lỗi xử lý chunk {chunk_id}: {e}")

    logger.info("🎉 [TTS] Hoàn tất toàn bộ chunks.")

def collect_audio_bytesio(transcript,redis_config):
    redis_conn = redis.Redis(**redis_config)
    audio_bytesio_list = []
    for idx in range(len(transcript)):
        chunk_id = f"{transcript[idx]['id']}"
        audio_bytes = redis_conn.get(f"audio:{chunk_id}")
        if audio_bytes:
            audio_bytesio_list.append(BytesIO(audio_bytes))
        else:
            logger.warning(f"❌ No audio for {chunk_id}")
    return audio_bytesio_list

def collect_merged_chunks_from_redis(transcript_chunks,  redis_config):
    redis_conn = redis.Redis(**redis_config)
    merged_chunks = []
    for chunk in transcript_chunks:
        chunk_id = f"{chunk['id']}"
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
    total_chunks = len(transcript_chunks)

    # Xóa queue cũ nếu có (tránh đụng độ job cũ)
    redis_conn = redis.Redis(**redis_config)
    redis_conn.delete("translation_queue")

    translator = multiprocessing.Process(
        target=translator_process,
        args=(transcript_chunks, translator_func, video_id, redis_config)
    )
    tts = multiprocessing.Process(
        target=tts_process,
        args=(video_id, redis_config, total_chunks)
    )

    translator.start()
    tts.start()

    translator.join()
    tts.join()  # Không terminate nữa → TTS tự thoát khi xong

    logger.info("🎉 Tất cả các tiến trình đã hoàn tất!")

    # In log độ dài audio
    for idx in range(len(transcript_chunks)):
        chunk_id = f"{transcript_chunks[idx]['id']}"
        audio = redis_conn.get(f"audio:{chunk_id}")
        print(f"{chunk_id} -> Audio Bytes Length: {len(audio) if audio else '❌ No audio'}")

    return {
        "transcriptAfterTranslated": collect_merged_chunks_from_redis(transcript_chunks, video_id, redis_config),
        "ListBytesIO": collect_audio_bytesio(transcript_chunks, video_id, redis_config)
    }
