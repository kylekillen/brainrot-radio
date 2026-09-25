"""Run dictation threads at user-interactive priority on macOS.

The Mac mini is heavily oversubscribed by fleet workers (load average ~19 on 12
cores). At default priority the same 15 s clip took 1.6-4 s to transcribe on CPU
under that load; at user-interactive QoS it took 0.4-1.2 s. Threads spawned after
the call (onnxruntime's pool, ffmpeg children) inherit the class.
"""
import ctypes
import sys

_QOS_CLASS_USER_INTERACTIVE = 0x21


def set_interactive() -> None:
    """Best-effort: mark the calling thread user-interactive; never raises."""
    if sys.platform != "darwin":
        return
    try:
        ctypes.CDLL("/usr/lib/libSystem.B.dylib").pthread_set_qos_class_self_np(_QOS_CLASS_USER_INTERACTIVE, 0)
    except Exception:  # noqa: BLE001
        pass
