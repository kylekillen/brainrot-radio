import importlib.util
import sys
from pathlib import Path

_p = Path(__file__).resolve().parents[1] / "code-voice" / "dictate_gateway.py"
_spec = importlib.util.spec_from_file_location("dictate_gateway", _p)
dg = importlib.util.module_from_spec(_spec)
sys.modules["dictate_gateway"] = dg
_spec.loader.exec_module(dg)


def test_chunks_keep_every_word():
    text = " ".join(f"Sentence number {i} has a few words." for i in range(120))
    chunks = dg._chunks(text)
    assert len(chunks) > 1
    assert " ".join(chunks).split() == text.split()


def test_cold_model_returns_raw_and_never_blocks(monkeypatch):
    monkeypatch.setattr(dg, "_model_loaded", lambda: False)
    monkeypatch.setattr(dg, "warm_model", lambda: None)
    text, status = dg.clean_text("um hello there", allow_cold=False)
    assert (text, status) == ("um hello there", "raw-cold")


def test_cleanup_that_drops_text_is_rejected(monkeypatch):
    monkeypatch.setattr(dg, "_model_loaded", lambda: True)
    monkeypatch.setattr(dg, "_chat", lambda *a, **k: "Summary.")
    raw = "so the second act needs a midpoint reversal where Dana finds out the letters were never real"
    text, status = dg.clean_text(raw, allow_cold=False)
    assert text == raw and status == "raw-error"


def test_cleanup_applied(monkeypatch):
    monkeypatch.setattr(dg, "_model_loaded", lambda: True)
    monkeypatch.setattr(dg, "_chat", lambda *a, **k: "Send the draft to Alyssa on Friday.")
    text, status = dg.clean_text("um send the draft to Alyssa on Thursday no wait Friday", allow_cold=False)
    assert status == "clean" and text.startswith("Send the draft")


def test_prefix_is_stripped():
    h = dg.Handler.__new__(dg.Handler)
    for path, want in [("/dictate/v1/audio/transcriptions?raw=1", "/v1/audio/transcriptions"),
                       ("/dictate", "/"), ("/v1/models", "/v1/models")]:
        h.path = path
        assert h._path() == want


def test_think_block_stripped(monkeypatch):
    monkeypatch.setattr(dg, "_post_json", lambda *a, **k: {"message": {"content": "<think>x</think>\n\nHello."}})
    assert dg._chat([], timeout=1) == "Hello."
