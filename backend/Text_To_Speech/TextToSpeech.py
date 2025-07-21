import os
import azure.cognitiveservices.speech as speechsdk
from typing import List, Dict, Optional
from io import BytesIO
from dotenv import load_dotenv
import logging

load_dotenv()

class TextToSpeechModule:
    """
    Module TTS được tối ưu cho lồng tiếng video YouTube
    """
    
    def __init__(self,
                 region: str = None,
                 text_to_speech_key: str = None,
                 output_format: str = "mp3",
                 voice: str = "vi-VN-HoaiMyNeural"):
        
        # Cải thiện: Validate tham số đầu vào
        self.region = region or os.getenv('TTS_REGION')
        self.key = text_to_speech_key or os.getenv('TEXT_TO_SPEECH_KEY')
        
        if not self.region or not self.key:
            raise ValueError("TTS_REGION và TEXT_TO_SPEECH_KEY phải được cung cấp")
        
        # Khởi tạo speech config
        self.speech_config = speechsdk.SpeechConfig(subscription=self.key, region=self.region)
        self.voice = voice
        self.default_cps = 15  # ký tự mỗi giây
        
        # Cache format để tránh set lại mỗi lần
        self.current_format = None
        self.output_format = output_format
        self._set_output_format(output_format)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)

    def _set_output_format(self, output_format: str):
        """Thiết lập định dạng output một cách tối ưu"""
        if self.current_format == output_format:
            return
            
        format_map = {
            "mp3": speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3,
            "wav": speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
        }
        
        if output_format not in format_map:
            raise ValueError(f"Unsupported output format: {output_format}. Supported: {list(format_map.keys())}")
        
        self.speech_config.set_speech_synthesis_output_format(format_map[output_format])
        self.current_format = output_format

    def calculate_rate_global(self, segments: List[Dict]) -> List[str]:
        """
        Tính toán tốc độ đọc cho từng segment dựa trên timing
        BUG FIXES:
        - Xử lý edge case khi segments rỗng
        - Validate dữ liệu đầu vào tốt hơn
        - Tối ưu thuật toán tính toán
        """
        if not segments:
            raise ValueError("Segments list cannot be empty")
        
        # Validate segments data
        for i, seg in enumerate(segments):
            if not all(key in seg for key in ['text', 'duration']):
                raise ValueError(f"Segment {i} missing required keys: 'text', 'duration'")
            if seg['duration'] <= 0:
                raise ValueError(f"Segment {i} has invalid duration: {seg['duration']}")
        
        total_chars = sum(len(seg['text'].strip()) for seg in segments if seg['text'].strip())
        total_duration = sum(seg['duration'] for seg in segments)
        
        if total_duration == 0 or total_chars == 0:
            self.logger.warning("Zero total duration or character count, using default rates")
            return ["0%"] * len(segments)

        avg_cps = total_chars / total_duration
        self.default_cps = avg_cps
        rates = []
        
        for i, seg in enumerate(segments):
            text_length = len(seg['text'].strip())
            if text_length == 0:
                rates.append("0%")
                continue
                
            seg_cps = text_length / seg['duration'] if seg['duration'] > 0 else avg_cps
            
            # Cải thiện: Làm mượt với trọng số
            weight = 0.7  # Trọng số cho segment cps vs avg cps
            smooth_cps = seg_cps * weight + avg_cps * (1 - weight)
            
            rate_factor = seg['duration'] / (text_length / smooth_cps)
            rate_percent = round((rate_factor - 1) * 100)
            
            # Giới hạn rate trong khoảng hợp lý
            rate_percent = max(-50, min(100, rate_percent))
            rates.append(f"{'+' if rate_percent > 0 else ''}{rate_percent}%")
            
        return rates

    def generate_ssml(self, segments: List[Dict]) -> str:
        """
        Tạo SSML với xử lý timing chính xác hơn
        BUG FIXES:
        - Xử lý trường hợp segments[0]['start'] không tồn tại
        - Escape XML characters trong text
        - Tối ưu xử lý break time
        """
        if not segments:
            raise ValueError("Segments cannot be empty")
            
        rates = self.calculate_rate_global(segments)

        ssml_parts = [
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="vi-VN">',
            f'<voice name="{self.voice}">'
        ]
        
        # Xử lý silence đầu nếu có
        first_start = segments[0].get('start', 0.0)
        if first_start > 0.1:  # Chỉ thêm break nếu > 100ms
            ssml_parts.append(f'<break time="{int(first_start * 1000)}ms"/>')
        
        for i, (seg, rate) in enumerate(zip(segments, rates)):
            # Escape XML characters
            text = self._escape_xml(seg['text'].strip())
            if text:  # Chỉ thêm nếu có text
                ssml_parts.append(f'<prosody rate="{rate}">{text}</prosody>')
            
            # Xử lý break time giữa các segments
            if i < len(segments) - 1:
                current_end = seg.get('start', 0) + seg.get('duration', 0)
                next_start = segments[i+1].get('start', current_end)
                break_time = next_start - current_end
                
                if break_time > 0.05:  # Chỉ thêm break nếu > 50ms
                    ssml_parts.append(f'<break time="{int(break_time * 1000)}ms"/>')
        
        ssml_parts.extend(['</voice>', '</speak>'])
        return "\n".join(ssml_parts)

    def _escape_xml(self, text: str) -> str:
        """Escape các ký tự đặc biệt trong XML"""
        return (text.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace('"', "&quot;")
                   .replace("'", "&apos;"))

    def ssml_to_bytesio(self, 
                       ssml_text: str,
                       audio_format: Optional[speechsdk.SpeechSynthesisOutputFormat] = None) -> Optional[BytesIO]:
        """
        Chuyển đổi SSML thành BytesIO
        BUG FIXES:
        - Tối ưu việc set format chỉ khi cần thiết
        - Cải thiện error handling
        - Thêm validation cho SSML
        """
        if not ssml_text.strip():
            raise ValueError("SSML text cannot be empty")
        
        try:
            # Chỉ set format nếu khác với format hiện tại
            if audio_format and audio_format != getattr(self.speech_config, '_output_format', None):
                self.speech_config.set_speech_synthesis_output_format(audio_format)
            
            # Tạo synthesizer
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config,
                audio_config=None  # None để lấy raw audio data
            )
            
            # Thực hiện synthesis
            result = synthesizer.speak_ssml_async(ssml_text).get()
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                if not result.audio_data:
                    self.logger.error("Audio data is empty")
                    return None
                    
                audio_bytes = BytesIO(result.audio_data)
                audio_bytes.seek(0)
                self.logger.info(f"TTS completed successfully, audio size: {len(result.audio_data)} bytes")
                return audio_bytes
                
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                error_msg = f"Speech synthesis canceled: {cancellation_details.reason}"
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    error_msg += f", Error details: {cancellation_details.error_details}"
                self.logger.error(error_msg)
                return None
                
            else:
                self.logger.error(f"Unexpected result reason: {result.reason}")
                return None
                
        except Exception as e:
            self.logger.error(f"TTS synthesis failed: {str(e)}", exc_info=True)
            return None

    def synthesize_to_file(self, ssml: str, output_file: str) -> bool:
        """
        Lưu SSML thành file âm thanh
        BUG FIXES:
        - Trả về boolean để indicate success/failure
        - Validate file path
        - Tốt hơn error handling
        """
        try:
            # Validate output path
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )
            
            result = synthesizer.speak_ssml_async(ssml).get()
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
                self.logger.info(f"✅ Audio saved: {output_file} ({file_size} bytes)")
                return True
            else:
                error_msg = f"TTS failed: {result.reason}"
                if result.reason == speechsdk.ResultReason.Canceled:
                    error_msg += f", Details: {result.cancellation_details.error_details}"
                self.logger.error(error_msg)
                return False
                
        except Exception as e:
            self.logger.error(f"File synthesis failed: {str(e)}", exc_info=True)
            return False

    def synthesize_to_speaker(self, ssml: str) -> bool:
        """
        Phát âm thanh qua loa
        BUG FIXES:
        - Trả về boolean
        - Cải thiện error handling
        """
        try:
            audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )
            
            result = synthesizer.speak_ssml_async(ssml).get()
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                self.logger.info("✅ Audio played successfully")
                return True
            else:
                self.logger.error(f"TTS playback failed: {result.reason}")
                return False
                
        except Exception as e:
            self.logger.error(f"Speaker synthesis failed: {str(e)}", exc_info=True)
            return False

    # Thêm method utility
    def get_supported_voices(self) -> List[str]:
        """Trả về danh sách voices tiếng Việt được hỗ trợ"""
        return [
            "vi-VN-HoaiMyNeural",
            "vi-VN-NamMinhNeural", 
            "vi-VN-HongNhungNeural",
            "vi-VN-ThuanNeural"
        ]
    
    def estimate_duration(self, text: str, rate_percent: int = 0) -> float:
        """Ước tính thời gian đọc văn bản"""
        char_count = len(text.strip())
        base_duration = char_count / self.default_cps
        
        # Điều chỉnh theo rate
        rate_factor = 1 + (rate_percent / 100)
        return base_duration / rate_factor if rate_factor > 0 else base_duration

# Ví dụ sử dụng với error handling tốt hơn
def example_usage():
    """Ví dụ sử dụng module được tối ưu"""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Khởi tạo module
        tts = TextToSpeechModule(
            output_format="mp3",
            voice="vi-VN-HoaiMyNeural"
        )
        
        # Sample segments với validation
        segments = [
            {"text": "Xin chào, đây là đoạn đầu tiên", "start": 0.0, "duration": 2.5},
            {"text": "Và đây là đoạn thứ hai", "start": 3.0, "duration": 2.0},
            {"text": "Cuối cùng là đoạn kết thúc", "start": 6.0, "duration": 2.2}
        ]
        
        # Generate SSML
        ssml = tts.generate_ssml(segments)
        print("Generated SSML:")
        print(ssml)
        
        # Convert to BytesIO
        audio_data = tts.ssml_to_bytesio(ssml)
        if audio_data:
            print(f"Audio generated: {len(audio_data.getvalue())} bytes")
        
    except Exception as e:
        logging.error(f"Example failed: {e}")

# if __name__ == "__main__":
#     example_usage()