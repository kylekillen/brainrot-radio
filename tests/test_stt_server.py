import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "code-voice"))
_spec = importlib.util.spec_from_file_location("stt_server", _root / "code-voice" / "stt_server.py")
stt = importlib.util.module_from_spec(_spec)
sys.modules["stt_server"] = stt
_spec.loader.exec_module(stt)


def test_tiny_upload_rejected_before_any_engine(monkeypatch):
    monkeypatch.setattr(stt, "transcribe_file", lambda *a, **k: pytest.fail("engine must not run"))
    with pytest.raises(stt.TinyUpload):
        stt.transcribe_bytes(b"audio-bytes", "dashboard.webm")


@pytest.mark.skipif(not Path(stt.FFMPEG).exists() and not shutil.which("ffmpeg"), reason="no ffmpeg")
def test_webm_is_transcoded_to_wav_before_engine(tmp_path, monkeypatch):
    src = tmp_path / "clip.webm"
    subprocess.run([stt.FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:a", "libopus", str(src)], check=True)
    seen = {}

    def fake(path):
        seen["path"] = path
        seen["riff"] = Path(path).read_bytes()[:4]
        return "ok"

    monkeypatch.setattr(stt, "_onnx_recognize", fake)
    monkeypatch.setattr(stt, "transcribe_file", lambda *a, **k: pytest.fail("MLX must not run when CPU works"))
    assert stt.transcribe_bytes(src.read_bytes(), "dictation.webm") == "ok"
    assert seen["path"].endswith(".wav") and seen["riff"] == b"RIFF"
    assert not Path(seen["path"]).exists()


def test_cpu_failure_falls_back_to_mlx_on_the_wav(tmp_path, monkeypatch):
    src = tmp_path / "clip.webm"
    subprocess.run([stt.FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:a", "libopus", str(src)], check=True)
    seen = {}
    monkeypatch.setattr(stt, "_onnx_recognize", lambda w: (_ for _ in ()).throw(RuntimeError("no onnx")))
    monkeypatch.setattr(stt, "transcribe_file", lambda path, model: seen.setdefault("p", path) and "mlx")
    assert stt.transcribe_bytes(src.read_bytes(), "dictation.webm") == "mlx"
    assert seen["p"].endswith(".wav")


def test_transcode_failure_passes_original_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(stt, "to_wav", lambda s, d: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(stt, "transcribe_file", lambda path, model: seen.setdefault("p", path) and "ok")
    assert stt.transcribe_bytes(b"x" * 2000, "a.webm") == "ok"
    assert seen["p"].endswith(".webm")
