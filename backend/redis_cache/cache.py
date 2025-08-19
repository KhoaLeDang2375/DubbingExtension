import multiprocessing
import redis
from io import BytesIO
from loguru import logger
from Handler_Transcript.Handler_Transcript import Handler
from fastapi import HTTPException
from Text_To_Speech.TextToSpeech import TextToSpeechModule
from typing import List, Dict
import json

# Push tất cả transcript chunk vào Redis
def push_all_chunks_to_redis(chunks: List[Dict], redis_config: dict):
    redis_conn = redis.Redis(**redis_config)
    try:
        for chunk in chunks:
            chunk_id = chunk['id']  # Ví dụ: abc123:0.00
            payload = chunk['chunk']  # Danh sách entry [{"text", "start", "end"}, ...]
            redis_conn.set(f"transcript:{chunk_id}", json.dumps(payload, ensure_ascii=False), ex=3600)
            redis_conn.lpush("transcript_chunk_queue", chunk_id)
        logger.info("✅ Đã đẩy tất cả transcript chunks vào Redis.")
    except Exception as e:
        logger.exception("❌ Lỗi khi push transcript chunks vào Redis.")

# Hàm dịch 1 chunk
def translate_chunk(chunk: List[Dict], translator_func, handler, source_lang, target_lang) -> List[Dict]:
    try:
        entries = chunk  # chunk là danh sách các câu nhỏ [{"text", ...}]
        texts = [entry["text"] for entry in entries]
        need_text_trans = ' '.join(texts)
        logger.info("📘 [Translator] Đang dịch chunk...")
        rawTextAfterTranslate = translator_func(texts=need_text_trans, source_lang=source_lang, target_langs=target_lang)
        return handler.merge_chunk_translation(chunk=entries, translated_result=rawTextAfterTranslate, target_language=target_lang)
    except Exception as e:
        logger.exception("❌ Lỗi khi dịch transcript.")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

# Tiến trình dịch transcript
def translator_process(list_chunks_id: List[str], translator_func, redis_config, source_lang, target_lang):
    redis_conn = redis.Redis(**redis_config)
    handler = Handler()

    for chunk_id in list_chunks_id:
        try:
            raw_chunk = redis_conn.get(f"transcript:{chunk_id}")
            if raw_chunk is None:
                logger.warning(f"[Translator] Không tìm thấy chunk: {chunk_id}")
                continue

            chunk_data = json.loads(raw_chunk)
            merged = translate_chunk(chunk_data, translator_func, handler, source_lang, target_lang)

            redis_conn.set(f"translation:{chunk_id}", json.dumps(merged, ensure_ascii=False), ex=3600)
            redis_conn.lpush("translation_queue", chunk_id)
            logger.info(f"✅ [Translator] Hoàn tất chunk: {chunk_id}")
        except Exception as e:
            logger.error(f"❌ [Translator] Lỗi chunk {chunk_id}: {e}")

# Tiến trình tạo audio từ bản dịch
def tts_process(redis_config: dict, total_chunks: int, tts_voice: str):
    redis_conn = redis.Redis(**redis_config)
    tts = TextToSpeechModule(voice=tts_voice, output_format="webm")

    logger.info("📗 [TTS] Bắt đầu lắng nghe queue...")

    processed_chunks = 0
    processed_set = set()

    while processed_chunks < total_chunks:
        result = redis_conn.brpop("translation_queue", timeout=10)
        if result is None:
            logger.warning("[TTS] Timeout khi chờ dữ liệu mới...")
            continue

        _, chunk_id_bytes = result
        chunk_id = chunk_id_bytes.decode("utf-8")

        if chunk_id in processed_set:
            logger.warning(f"[TTS] Chunk {chunk_id} đã xử lý, bỏ qua.")
            continue

        try:
            translated_bytes = redis_conn.get(f"translation:{chunk_id}")
            if not translated_bytes:
                logger.error(f"[TTS] Không tìm thấy bản dịch cho {chunk_id}")
                continue
            logger.info(f"[TTS] Dang xử lý xong chunk: {chunk_id}")
            merged_chunk = json.loads(translated_bytes)
            ssml = tts.generate_ssml(merged_chunk)
            audio_bytesio = tts.ssml_to_bytesio(ssml)
            redis_conn.set(f"audio:{chunk_id}", audio_bytesio.getvalue(), ex=3600)

            logger.info(f"✅ [TTS] Đã xử lý xong chunk: {chunk_id}")

            processed_chunks += 1
            processed_set.add(chunk_id)

        except Exception as e:
            logger.error(f"[TTS] Lỗi xử lý chunk {chunk_id}: {e}")

    logger.info("🎉 [TTS] Hoàn tất toàn bộ chunks.")

# Lấy danh sách audio BytesIO từ Redis
from typing import Any

def collect_audio_bytes_and_duration(list_chunk_ids: List[str], redis_config: dict) -> List[Dict[str, Any]]:
    redis_conn = redis.Redis(**redis_config)
    result = []

    for chunk_id in list_chunk_ids:
        audio_bytes = redis_conn.get(f"audio:{chunk_id}")
        if not audio_bytes:
            logger.warning(f"❌ Không tìm thấy audio cho {chunk_id}")
            continue

        audio_io = BytesIO(audio_bytes)


        result.append({
            "chunk_id": chunk_id,
            "audio_bytesio": audio_io,
        })
    return result

# Lấy bản dịch đã merge từ Redis
def collect_merged_chunks_from_redis(list_chunk_ids: List[str], redis_config: dict) -> List[Dict]:
    redis_conn = redis.Redis(**redis_config)
    merged_chunks = []

    for chunk_id in list_chunk_ids:
        merged_bytes = redis_conn.get(f"translation:{chunk_id}")
        if merged_bytes:
            try:
                merged_chunk = json.loads(merged_bytes)
                merged_chunks.append(merged_chunk)
            except Exception as e:
                logger.error(f"❌ Lỗi khi decode merged chunk {chunk_id}: {e}")
        else:
            logger.warning(f"❌ Không tìm thấy merged chunk cho {chunk_id}")
    return merged_chunks

# Hàm chính điều phối 2 tiến trình dịch và TTS
def multiprocessingForTTSAndTranslator(
    list_chunk_ids: List[str],
    translator_func,
    video_id: str,
    redis_config: dict,
    source_lang: str,
    target_lang: str,
    tts_voice: str
):
    total_chunks = len(list_chunk_ids)
    redis_conn = redis.Redis(**redis_config)

    # Dọn queue cũ
    redis_conn.delete("translation_queue")

    translator = multiprocessing.Process(
        target=translator_process,
        args=(list_chunk_ids, translator_func, redis_config, source_lang, target_lang)
    )
    tts = multiprocessing.Process(
        target=tts_process,
        args=(redis_config, total_chunks, tts_voice)
    )

    translator.start()
    tts.start()

    translator.join()
    if translator.exitcode != 0:
        logger.error("❌ Translator process exited with error!")

    tts.join()
    if tts.exitcode != 0:
        logger.error("❌ TTS process exited with error!")

    logger.info("🎉 Tất cả các tiến trình đã hoàn tất!")

    for chunk_id in list_chunk_ids:
        audio = redis_conn.get(f"audio:{chunk_id}")
        print(f"{chunk_id} -> Audio Bytes Length: {len(audio) if audio else '❌ No audio'}")

    return {
        "audio_chunks": collect_audio_bytes_and_duration(list_chunk_ids, redis_config)
    }
