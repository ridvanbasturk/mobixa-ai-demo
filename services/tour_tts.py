"""Tur videoları için seslendirme (TTS) katmanı.

Takılabilir (pluggable) tasarlanmıştır: bugün Amazon Polly kullanılır, yarın
başka bir motor eklemek için yalnızca yeni bir sınıf yazmak yeterlidir.

ÖNEMLİ — zarif düşüş (graceful degradation):
Polly, Bedrock Mantle'dan AYRI bir AWS servisidir ve projenin
`OPENAI_API_KEY`'i ile ÇALIŞMAZ; kendi AWS kimlik bilgilerini ister. Bu
kimlik bilgileri yoksa boru hattı ÇÖKMEZ — `NullTTS` devreye girer, video
sessiz ama altyazılı üretilir ve nedeni arayüzde açıkça gösterilir.

NOT: Polly'de Türkçe YALNIZCA "Filiz" sesidir ve nöral motoru desteklemez;
İngilizcede nöral ses mevcuttur. Bu fark `.env.example`'da da belgelenmiştir.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Ses üretilemediğinde bir adımın kaç saniye tutulacağı (kelime sayısına göre
# tahmin edilir; bu değerler sessiz videonun da izlenebilir olmasını sağlar).
SILENT_SECONDS_PER_WORD = 0.38
SILENT_MIN_SECONDS = 2.4
SILENT_MAX_SECONDS = 11.0


@dataclass
class SpeechResult:
    """Tek bir anlatım cümlesinin seslendirme sonucu."""

    audio_path: Optional[Path]
    duration_seconds: float
    voiced: bool
    error: Optional[str] = None


def estimate_silent_duration(text: str) -> float:
    """Ses yokken bir adımın ne kadar tutulacağını tahmin eder."""
    words = len((text or "").split())
    estimated = words * SILENT_SECONDS_PER_WORD
    return max(SILENT_MIN_SECONDS, min(SILENT_MAX_SECONDS, estimated))


def probe_audio_duration(audio_path: Path) -> Optional[float]:
    """ffprobe ile ses dosyasının gerçek süresini ölçer."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return float((result.stdout or "").strip())
    except ValueError:
        return None


class NullTTS:
    """Ses üretmeyen yedek motor — video sessiz ama altyazılı kalır."""

    def __init__(self, reason: str = "Seslendirme yapılandırılmamış."):
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    @property
    def description(self) -> str:
        return self.reason

    def synthesize(self, text: str, language: str, output_path: Path) -> SpeechResult:
        return SpeechResult(
            audio_path=None,
            duration_seconds=estimate_silent_duration(text),
            voiced=False,
            error=self.reason,
        )


class PollyTTS:
    """Amazon Polly seslendirmesi (boto3 üzerinden)."""

    def __init__(self, region: Optional[str] = None):
        self.region = region or os.environ.get("POLLY_REGION") or os.environ.get("AWS_REGION", "eu-central-1")
        self._client = None
        self._error: Optional[str] = None

    def _voice_for(self, language: str) -> tuple:
        if language == "en":
            return (
                os.environ.get("POLLY_VOICE_EN", "Joanna"),
                os.environ.get("POLLY_ENGINE_EN", "neural"),
            )
        # Polly'de Türkçe yalnızca Filiz'tir ve nöral motoru yoktur.
        return (
            os.environ.get("POLLY_VOICE_TR", "Filiz"),
            os.environ.get("POLLY_ENGINE_TR", "standard"),
        )

    def _ensure_client(self):
        if self._client is not None or self._error is not None:
            return self._client
        try:
            import boto3  # noqa: PLC0415 - isteğe bağlı bağımlılık
        except ImportError:
            self._error = "boto3 kurulu değil (pip install boto3)."
            return None
        try:
            client = boto3.client("polly", region_name=self.region)
            # Ucuz bir çağrıyla kimlik bilgilerini gerçekten doğrula.
            client.describe_voices(LanguageCode="tr-TR")
            self._client = client
        except Exception as exc:  # noqa: BLE001 - her tür kimlik/ağ hatası
            self._error = f"Amazon Polly'ye erişilemedi: {type(exc).__name__}"
        return self._client

    @property
    def available(self) -> bool:
        return self._ensure_client() is not None

    @property
    def description(self) -> str:
        if self.available:
            return f"Amazon Polly hazır ({self.region})"
        return self._error or "Amazon Polly kullanılamıyor."

    def synthesize(self, text: str, language: str, output_path: Path) -> SpeechResult:
        client = self._ensure_client()
        if client is None:
            return SpeechResult(
                audio_path=None,
                duration_seconds=estimate_silent_duration(text),
                voiced=False,
                error=self._error,
            )

        voice_id, engine = self._voice_for(language)
        try:
            response = client.synthesize_speech(
                Text=text,
                OutputFormat="mp3",
                VoiceId=voice_id,
                Engine=engine,
            )
            audio_stream = response.get("AudioStream")
            if audio_stream is None:
                raise RuntimeError("Polly yanıtında AudioStream yok")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_stream.read())
        except Exception as exc:  # noqa: BLE001
            return SpeechResult(
                audio_path=None,
                duration_seconds=estimate_silent_duration(text),
                voiced=False,
                error=f"Polly seslendirme hatası: {type(exc).__name__}",
            )

        duration = probe_audio_duration(output_path)
        if duration is None or duration <= 0:
            duration = estimate_silent_duration(text)
        # Anlatım bittikten sonra kısa bir nefes payı bırak.
        return SpeechResult(audio_path=output_path, duration_seconds=duration + 0.6, voiced=True)


def get_tts_engine(prefer_polly: bool = True):
    """Kullanılabilir en iyi motoru döner; hiçbiri yoksa NullTTS."""
    if prefer_polly:
        polly = PollyTTS()
        if polly.available:
            return polly
        return NullTTS(polly.description)
    return NullTTS("Seslendirme kapalı (kullanıcı tercihi).")
