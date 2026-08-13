"""Seslendirme katmanı testleri — gerçek AWS çağrısı YAPILMAZ.

En kritik davranış: Polly kimlik bilgisi olmadığında boru hattı ÇÖKMEZ,
sessiz + altyazılı videoya düşer ve nedenini açıkça bildirir.
"""
from __future__ import annotations

import services.tour_tts as tour_tts
from services.tour_tts import (
    NullTTS,
    PollyTTS,
    SpeechResult,
    estimate_silent_duration,
    get_tts_engine,
)


class _FakeAudioStream:
    def __init__(self, payload: bytes = b"ID3fake-mp3"):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class _FakePollyClient:
    def __init__(self, fail_on_synthesize: bool = False):
        self.fail_on_synthesize = fail_on_synthesize
        self.calls = []

    def describe_voices(self, **kwargs):
        return {"Voices": [{"Id": "Filiz"}]}

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_on_synthesize:
            raise RuntimeError("Polly patladı")
        return {"AudioStream": _FakeAudioStream()}


def _install_fake_boto3(monkeypatch, client):
    import sys
    import types

    module = types.ModuleType("boto3")
    module.client = lambda service, region_name=None: client
    monkeypatch.setitem(sys.modules, "boto3", module)


def test_null_tts_is_never_voiced_but_still_gives_a_duration():
    engine = NullTTS("Kimlik bilgisi yok.")
    result = engine.synthesize("Bu bir anlatım cümlesidir.", "tr", None)
    assert result.voiced is False
    assert result.audio_path is None
    assert result.duration_seconds > 0
    assert engine.available is False
    assert "Kimlik bilgisi yok." in engine.description


def test_silent_duration_scales_with_word_count_within_bounds():
    short = estimate_silent_duration("Kısa.")
    long = estimate_silent_duration(" ".join(["kelime"] * 40))
    assert short < long
    assert short >= tour_tts.SILENT_MIN_SECONDS
    assert long <= tour_tts.SILENT_MAX_SECONDS


def test_polly_unavailable_when_boto3_missing(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "boto3", None)
    engine = PollyTTS()
    # None modül import edilince ImportError yerine TypeError/AttributeError
    # olabilir; her koşulda "kullanılamıyor" davranışı beklenir.
    assert engine.available is False
    assert engine.description


def test_get_tts_engine_falls_back_to_null_when_polly_unavailable(monkeypatch):
    monkeypatch.setattr(PollyTTS, "available", property(lambda self: False))
    monkeypatch.setattr(PollyTTS, "description", property(lambda self: "Polly yok"))
    engine = get_tts_engine(prefer_polly=True)
    assert isinstance(engine, NullTTS)
    assert "Polly yok" in engine.description


def test_get_tts_engine_returns_null_when_voice_disabled():
    engine = get_tts_engine(prefer_polly=False)
    assert isinstance(engine, NullTTS)


def test_polly_synthesizes_and_writes_audio(monkeypatch, tmp_path):
    client = _FakePollyClient()
    _install_fake_boto3(monkeypatch, client)
    monkeypatch.setattr(tour_tts, "probe_audio_duration", lambda path: 3.0)

    engine = PollyTTS(region="eu-central-1")
    output = tmp_path / "step_01.mp3"
    result = engine.synthesize("Merhaba dünya.", "tr", output)

    assert result.voiced is True
    assert output.exists()
    assert output.read_bytes() == b"ID3fake-mp3"
    assert result.duration_seconds > 3.0  # nefes payı eklenir


def test_polly_uses_filiz_standard_for_turkish(monkeypatch, tmp_path):
    # Polly'de Türkçe YALNIZCA Filiz'tir ve nöral motoru desteklemez.
    client = _FakePollyClient()
    _install_fake_boto3(monkeypatch, client)
    monkeypatch.delenv("POLLY_VOICE_TR", raising=False)
    monkeypatch.delenv("POLLY_ENGINE_TR", raising=False)
    monkeypatch.setattr(tour_tts, "probe_audio_duration", lambda path: 2.0)

    PollyTTS().synthesize("Merhaba.", "tr", tmp_path / "a.mp3")
    assert client.calls[0]["VoiceId"] == "Filiz"
    assert client.calls[0]["Engine"] == "standard"


def test_polly_uses_neural_voice_for_english(monkeypatch, tmp_path):
    client = _FakePollyClient()
    _install_fake_boto3(monkeypatch, client)
    monkeypatch.delenv("POLLY_VOICE_EN", raising=False)
    monkeypatch.delenv("POLLY_ENGINE_EN", raising=False)
    monkeypatch.setattr(tour_tts, "probe_audio_duration", lambda path: 2.0)

    PollyTTS().synthesize("Hello.", "en", tmp_path / "b.mp3")
    assert client.calls[0]["VoiceId"] == "Joanna"
    assert client.calls[0]["Engine"] == "neural"


def test_polly_synthesis_failure_degrades_to_silent(monkeypatch, tmp_path):
    client = _FakePollyClient(fail_on_synthesize=True)
    _install_fake_boto3(monkeypatch, client)

    result = PollyTTS().synthesize("Merhaba.", "tr", tmp_path / "c.mp3")
    assert result.voiced is False
    assert result.audio_path is None
    assert result.duration_seconds > 0  # video yine de akmalı
    assert "Polly seslendirme hatası" in (result.error or "")


def test_speech_result_dataclass_defaults():
    result = SpeechResult(audio_path=None, duration_seconds=1.0, voiced=False)
    assert result.error is None
