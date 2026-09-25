import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code-voice"))
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


def test_cleanup_budget_caps_wait_and_returns_raw(monkeypatch):
    monkeypatch.setattr(dg, "_model_loaded", lambda: True)
    seen = {}

    def slow(msgs, timeout, **k):
        seen["timeout"] = timeout
        raise TimeoutError("timed out")

    monkeypatch.setattr(dg, "_chat", slow)
    text, status = dg.clean_text("um hello there friend", allow_cold=True)
    assert (text, status) == ("um hello there friend", "raw-error")
    assert seen["timeout"] <= dg.CLEAN_BUDGET


def test_small_instruct_model_call_omits_think_flag(monkeypatch):
    sent = {}
    monkeypatch.setattr(dg, "_post_json", lambda url, payload, t: sent.update(payload) or {"message": {"content": "ok"}})
    dg._chat([], timeout=1)
    assert "think" not in sent
    dg._chat([], timeout=1, think=False)
    assert sent["think"] is False


def test_tiny_upload_is_rejected_with_400():
    h = dg.Handler.__new__(dg.Handler)
    h.headers = {"Content-Length": "260"}
    h.rfile = __import__("io").BytesIO(b"x" * 260)
    got = {}
    h._json = lambda code, obj: got.update(code=code, obj=obj)
    h._transcribe()
    assert got["code"] == 400 and "too short" in got["obj"]["error"]
