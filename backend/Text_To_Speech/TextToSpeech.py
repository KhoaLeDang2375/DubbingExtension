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
        
        self.region = region or os.getenv('TTS_REGION')
        self.key = text_to_speech_key or os.getenv('TEXT_TO_SPEECH_KEY')
        if not self.region or not self.key:
            raise ValueError("TTS_REGION và TEXT_TO_SPEECH_KEY phải được cung cấp")

        self.speech_config = speechsdk.SpeechConfig(subscription=self.key, region=self.region)
        self.voice = voice
        self.default_cps = 10  # ký tự mỗi giây
        self.current_format = None
        self.output_format = output_format
        self._set_output_format(output_format)
        self.logger = logging.getLogger(__name__)

    def _safe_strip(self, value: Optional[str]) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _set_output_format(self, output_format: str):
        if self.current_format == output_format:
            return
        
        format_map = {
            "mp3": speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3,
            "wav": speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm,
            "webm": speechsdk.SpeechSynthesisOutputFormat.Webm16Khz16BitMonoOpus,
            "ogg": speechsdk.SpeechSynthesisOutputFormat.Ogg16Khz16BitMonoOpus
        }

        if output_format not in format_map:
            raise ValueError(f"Unsupported output format: {output_format}. Supported: {list(format_map.keys())}")

        self.speech_config.set_speech_synthesis_output_format(format_map[output_format])
        self.current_format = output_format

    def calculate_rate_global(self, segments: List[Dict]) -> List[str]:
        if not segments:
            raise ValueError("Segments list cannot be empty")

        for i, seg in enumerate(segments):
            if not all(key in seg for key in ['text_translated', 'duration']):
                raise ValueError(f"Segment {i} missing keys: 'text_translated', 'duration'")
            if seg['duration'] <= 0:
                raise ValueError(f"Segment {i} has invalid duration: {seg['duration']}")

        total_chars = sum(len(self._safe_strip(seg.get('text_translated'))) for seg in segments)
        total_duration = sum(seg['duration'] for seg in segments)

        if total_duration == 0 or total_chars == 0:
            self.logger.warning("Zero total duration or character count, using default rates")
            return ["0%"] * len(segments)

        avg_cps = total_chars / total_duration
        self.default_cps = avg_cps
        rates = []

        for seg in segments:
            text_len = len(self._safe_strip(seg.get('text_translated')))
            if text_len == 0:
                rates.append("0%")
                continue

            seg_cps = text_len / seg['duration']
            smooth_cps = seg_cps * 0.7 + avg_cps * 0.3
            rate_factor = seg['duration'] / (text_len / smooth_cps)
            rate_percent = round((rate_factor - 1) * 100)
            rate_percent = max(-30, min(50, rate_percent))
            rates.append(f"{'+' if rate_percent > 0 else ''}{rate_percent}%")

        return rates

    def generate_ssml(self, segments: List[Dict]) -> str:
        if not segments:
            raise ValueError("Segments cannot be empty")

        rates = self.calculate_rate_global(segments)
        ssml_parts = [
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="vi-VN">',
            f'<voice name="{self.voice}">'
        ]

        first_start = segments[0].get('start', 0.0)
        if first_start > 0.1:
            ssml_parts.append(f'<break time="{int(first_start * 1000)}ms"/>')

        for i, (seg, rate) in enumerate(zip(segments, rates)):
            text = self._escape_xml(self._safe_strip(seg.get('text_translated')))
            if text:
                ssml_parts.append(f'<prosody rate="{rate}">{text}</prosody>')

            if i < len(segments) - 1:
                current_end = seg.get('start', 0) + seg.get('duration', 0)
                next_start = segments[i+1].get('start', current_end)
                gap = next_start - current_end
                if 0.3 < gap < 5.0:
                    ssml_parts.append(f'<break time="{int(gap * 1000)}ms"/>')

        ssml_parts.extend(['</voice>', '</speak>'])
        return "\n".join(ssml_parts)

    def _escape_xml(self, text: str) -> str:
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                    .replace("'", "&apos;"))

    def ssml_to_bytesio(self, ssml_text: str,
                        audio_format: Optional[speechsdk.SpeechSynthesisOutputFormat] = None) -> Optional[BytesIO]:
        if not ssml_text.strip():
            raise ValueError("SSML text cannot be empty")

        try:
            if audio_format and audio_format != getattr(self.speech_config, '_output_format', None):
                self.speech_config.set_speech_synthesis_output_format(audio_format)

            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config, audio_config=None
            )

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
                details = result.cancellation_details
                msg = f"TTS canceled: {details.reason}, Details: {details.error_details}"
                self.logger.error(msg)
                return None

            self.logger.error(f"Unexpected TTS result: {result.reason}")
            return None

        except Exception as e:
            self.logger.error(f"TTS synthesis failed: {str(e)}", exc_info=True)
            return None

    def synthesize_to_file(self, ssml: str, output_file: str) -> bool:
        try:
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

            msg = f"TTS failed: {result.reason}"
            if result.reason == speechsdk.ResultReason.Canceled:
                msg += f", Details: {result.cancellation_details.error_details}"
            self.logger.error(msg)
            return False

        except Exception as e:
            self.logger.error(f"File synthesis failed: {str(e)}", exc_info=True)
            return False

    def synthesize_to_speaker(self, ssml: str) -> bool:
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

    def get_supported_voices(self) -> List[str]:
        return [
            "vi-VN-HoaiMyNeural",
            "vi-VN-NamMinhNeural", 
            "vi-VN-HongNhungNeural",
            "vi-VN-ThuanNeural"
        ]

    def estimate_duration(self, text: str, rate_percent: int = 0) -> float:
        text_clean = self._safe_strip(text)
        char_count = len(text_clean)
        base_duration = char_count / self.default_cps if self.default_cps else 1.0
        rate_factor = 1 + (rate_percent / 100)
        return base_duration / rate_factor if rate_factor > 0 else base_duration

