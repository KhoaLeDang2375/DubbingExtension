from loguru import logger
from typing import List, Dict
from fastapi import HTTPException
class Handler:   
    def split_transcript(self, entries, video_id, max_chars=2000, max_items=100):
        chunks = []
        current_chunk = []
        current_chunk_len = 0
        index = 0
        for entry in entries:
            sentence = entry['text'].strip()
            sentence_len = len(sentence)
            # Giữ lại dict gốc thay vì chỉ text
            if (current_chunk_len + sentence_len <= max_chars) and (len(current_chunk) < max_items):
                current_chunk.append(entry)
                current_chunk_len += sentence_len + 1
            else:
                index += 1
                chunks.append({'id': f'{video_id}_{index}', "chunk": current_chunk})
                current_chunk = [entry]
                current_chunk_len = sentence_len + 1
        if current_chunk:
            index += 1
            chunks.append({'id': f'{video_id}_{index}', "chunk": current_chunk})
        return chunks
    def merge_chunk_translation(self, chunk: List[Dict], translated_result: List[Dict], target_language: str = "vi") -> List[Dict]:
        """
        Merge dữ liệu chunk gốc và kết quả dịch từ translator (Azure hoặc GenAI).
        Đảm bảo mỗi entry có text_translated, start, duration cho TTS.

        Args:
            chunk: List[Dict] - danh sách các câu gốc [{text, start, duration, ...}]
            translated_result: List[Dict] - kết quả dịch [{lang_code: translated_text}, ...]
            target_language: str - mã ngôn ngữ đích

        Returns:
            List[Dict] - danh sách entry đã merge, mỗi entry có text_translated, start, duration
        """
        if not chunk or not translated_result or len(chunk) != len(translated_result):
            raise ValueError("Số lượng câu gốc và câu đã dịch không khớp.")

        merged = []
        for entry, trans in zip(chunk, translated_result):
            new_entry = {
                "text_translated": trans.get(target_language) if isinstance(trans, dict) else trans,
                "start": entry.get("start"),
                "duration": entry.get("duration")
            }
            merged.append(new_entry)
        return merged
    def mergeTranslatedTextToTranscript(self, transcript: List[Dict], merged_chunks: List[List[Dict]]) -> List[Dict]:
        """
        Cập nhật transcript gốc với trường text_translated từ danh sách các kết quả merge_chunk_translation.

        Args:
            transcript: List[Dict] - transcript gốc [{text, start, duration, ...}]
            merged_chunks: List[List[Dict]] - danh sách các chunk đã merge, mỗi chunk là list entry có text_translated

        Returns:
            List[Dict] - transcript đã cập nhật text_translated
        """
        # Flatten merged_chunks thành một list các entry đã dịch
        merged_entries = [entry for chunk in merged_chunks for entry in chunk]
        if len(transcript) != len(merged_entries):
            raise ValueError("⚠️ Số lượng entry gốc và entry đã dịch không khớp.")

        updated_transcript = []
        for orig_entry, merged_entry in zip(transcript, merged_entries):
            new_entry = orig_entry.copy()
            new_entry['text_translated'] = merged_entry.get('text_translated')
            updated_transcript.append(new_entry)
        return updated_transcript
