import os
import azure.cognitiveservices.speech as speechsdk
from typing import List, Dict
from io import BytesIO
from dotenv import load_dotenv
load_dotenv()

class TextToSpeechModule:
    def __init__(self,
                 region=os.getenv('TTS_REGION'),
                 TextToSpeechKey=os.getenv('TEXT_TO_SPEECH_KEY'),
                 output_format: str = "mp3",
                 voice: str = "vi-VN-HoaiMyNeural"):
        self.speech_config = speechsdk.SpeechConfig(subscription=TextToSpeechKey, region=region)
        self.voice = voice
        self.default_cps = 15  # ký tự mỗi giây

        # Cài định dạng đầu ra
        if output_format == "mp3":
            self.speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
            )
        elif output_format == "wav":
            self.speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
            )
        else:
            raise ValueError("Unsupported output format")

    def calculate_rate_global(self, segments: List[Dict]) -> List[str]:
        """
        Tính rate cho từng segment dựa vào tốc độ trung bình toàn bộ transcript.
        Trả về danh sách các rate string, ví dụ: ['+10%', '-20%', ...]
        """
        total_chars = sum(len(seg['text']) for seg in segments)
        total_duration = sum(seg['duration'] for seg in segments)

        if total_duration == 0 or total_chars == 0:
            raise ValueError("Invalid segment: zero total duration or character count")

        avg_cps = total_chars / total_duration
        self.default_cps = avg_cps
        rates = []
        for seg in segments:
            expected_duration = len(seg['text']) / avg_cps
            rate_factor = seg['duration'] / expected_duration
            rate_percent = round((rate_factor - 1) * 100)

            # Giới hạn rate để tránh quá nhanh hoặc quá chậm
            rate_percent = max(-100, min(100, rate_percent))
            rates.append(f"{'+' if rate_percent > 0 else ''}{rate_percent}%")

        return rates
    def generate_ssml(self, segments: List[Dict]) -> str:
        rates = self.calculate_rate_global(segments)

        ssml = [f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
                f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="vi-VN">']
        ssml.append(f'<voice name="{self.voice}">')

        for i, (seg, rate) in enumerate(zip(segments, rates)):
            ssml.append(f'<prosody rate="{rate}">{seg["text"]}</prosody>')
            if i < len(segments) - 1:
                ssml.append('<break time="300ms"/>')

        ssml.append('</voice>')
        ssml.append('</speak>')
        return "\n".join(ssml)

    def synthesize_to_file(self, ssml: str, output_file: str):
        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )
        result = synthesizer.speak_ssml_async(ssml).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print(f"✅ Đã lưu âm thanh tại: {output_file}")
        else:
            raise RuntimeError(f"TTS failed: {result.reason}")

    def synthesize_to_bytesio(self, ssml: str) -> BytesIO:
        stream = speechsdk.audio.PullAudioOutputStream.create_pull_stream()
        audio_config = speechsdk.audio.AudioOutputConfig(stream=stream)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )
        result = synthesizer.speak_ssml_async(ssml).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise RuntimeError(f"TTS failed: {result.reason}")

        audio_data_stream = speechsdk.AudioDataStream(result)
        audio_bytes = BytesIO()
        audio_data_stream.save_to_wave_stream(audio_bytes)
        audio_bytes.seek(0)
        return audio_bytes

    def synthesize_to_speaker(self, ssml: str):
        audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )
        result = synthesizer.speak_ssml_async(ssml).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise RuntimeError(f"TTS playback failed: {result.reason}")
        print("✅ Âm thanh đã được phát ra loa thành công.")


