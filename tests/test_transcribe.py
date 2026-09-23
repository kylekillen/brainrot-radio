"""Unit tests for the local STT engine adapter."""

import transcribe


def test_result_text_accepts_whisper_mapping():
    assert transcribe._result_text({"text": "  hello  ", "segments": []}) == "hello"


def test_result_text_accepts_parakeet_aligned_result():
    class Aligned:
        text = "  hello from parakeet  "
        sentences = []

    assert transcribe._result_text(Aligned()) == "hello from parakeet"


def test_primary_failure_falls_back_to_whisper(monkeypatch):
    calls = []

    def fake_run(path, model):
        calls.append((path, model))
        if model == transcribe.PRIMARY_MODEL:
            raise RuntimeError("primary unavailable")
        return "fallback text"

    monkeypatch.setattr(transcribe, "_run_model", fake_run)
    assert transcribe.transcribe("audio.ogg") == "fallback text"
    assert calls == [
        ("audio.ogg", transcribe.PRIMARY_MODEL),
        ("audio.ogg", transcribe.FALLBACK_MODEL),
    ]


def test_explicit_whisper_model_does_not_retry_primary(monkeypatch):
    calls = []

    def fake_run(path, model):
        calls.append((path, model))
        return "whisper text"

    monkeypatch.setattr(transcribe, "_run_model", fake_run)
    assert transcribe.transcribe("audio.ogg", model=transcribe.FALLBACK_MODEL) == "whisper text"
    assert calls == [("audio.ogg", transcribe.FALLBACK_MODEL)]


def test_default_is_parakeet():
    assert transcribe.MODEL == transcribe.PRIMARY_MODEL
    assert transcribe.PRIMARY_MODEL != transcribe.FALLBACK_MODEL
