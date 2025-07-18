class Handler:   
    def mergeTranslatedTextToTranscript(self,transcript, listTextAfterTranslated):
            """
            Gắn kết quả dịch từ listTextAfterTranslated vào từng entry của transcript gốc.

            Args:
                transcript: List[Dict] — các đoạn văn bản gốc [{text, start, duration, ...}]
                listTextAfterTranslated: List[List[str]] — các đoạn văn bản đã dịch (theo chunk)

            Returns:
                List[Dict] — transcript có thêm field `text_vi` là bản dịch.
            """
            merged_transcript = []
            flat_translations = [text for chunk in listTextAfterTranslated for text in chunk]

            if len(flat_translations) != len(transcript):
                raise ValueError("⚠️ Số câu đã dịch không khớp với số câu trong transcript.")

            for i, entry in enumerate(transcript):
                new_entry = entry.copy()
                new_entry['text_vi'] = flat_translations[i]
                merged_transcript.append(new_entry)

            return merged_transcript
    def split_transcript(self, entries, max_chars=4500, max_items=100):
        """
        Chia transcript đầu vào thành các chunk,
        mỗi chunk là list các dict gốc: {text, start, duration},
        sao cho tổng độ dài text trong 1 chunk không vượt quá max_chars.
        """
        chunks = []
        current_chunk = []
        current_chunk_len = 0

        for entry in entries:
            sentence = entry['text'].strip()
            sentence_len = len(sentence)

            # Nếu còn chỗ trong chunk hiện tại
            if (current_chunk_len + sentence_len <= max_chars) and (len(current_chunk) < max_items):
                current_chunk.append(entry['text'])
                current_chunk_len += sentence_len + 1
            else:
                # Đóng chunk lại và bắt đầu chunk mới
                chunks.append(current_chunk)
                current_chunk = [entry['text']]
                current_chunk_len = sentence_len + 1

        # Thêm chunk cuối nếu còn
        if current_chunk:
            chunks.append(current_chunk)

        return chunks