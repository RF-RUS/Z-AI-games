"""Snapshot logic in api.perceive: screenshot bytes are read into a temp file
at request start so that PIL Image.open() never races against the adapter
cleaning up / overwriting evidence-*.png during a long VLM timeout.
"""
import os
import tempfile

from PIL import Image


def _write_png(path: str, size: tuple[int, int] = (16, 16)) -> None:
    Image.new("RGB", size, (120, 80, 200)).save(path)


# ── Snapshot logic (mirrors api.perceive lines 64-73) ─────────────────────

def _snapshot(screenshot_path: str) -> tuple[str, str]:
    """Return (snap_path, new_screenshot_path).  Caller must unlink snap_path."""
    with open(screenshot_path, "rb") as fh:
        raw = fh.read()
    fd, snap = tempfile.mkstemp(suffix=".png")
    os.write(fd, raw)
    os.close(fd)
    return snap, snap


def test_snapshot_survives_source_deletion(tmp_path):
    """PIL must open the snapshot even after the original evidence file is deleted."""
    src = str(tmp_path / "evidence.png")
    _write_png(src)

    snap, new_path = _snapshot(src)
    try:
        # Simulate adapter cleaning up the evidence file mid-request
        os.unlink(src)
        assert not os.path.exists(src), "original should be gone"

        # Snapshot must still be a valid image
        with Image.open(new_path) as img:
            assert img.size == (16, 16)
    finally:
        if os.path.exists(snap):
            os.unlink(snap)


def test_snapshot_is_independent_copy(tmp_path):
    """Overwriting the source after snapshotting must not corrupt the snapshot."""
    src = str(tmp_path / "evidence.png")
    _write_png(src, size=(8, 8))

    snap, new_path = _snapshot(src)
    try:
        # Overwrite the source with a different image
        _write_png(src, size=(32, 32))

        # Snapshot still reflects the original (8×8)
        with Image.open(new_path) as img:
            assert img.size == (8, 8)
    finally:
        if os.path.exists(snap):
            os.unlink(snap)


def test_snapshot_cleanup_in_finally(tmp_path):
    """Temp file is removed in the finally block even when downstream raises."""
    src = str(tmp_path / "evidence.png")
    _write_png(src)

    snap = None
    try:
        snap, _ = _snapshot(src)
        assert os.path.exists(snap)
        raise RuntimeError("simulated downstream error")
    except RuntimeError:
        pass
    finally:
        if snap and os.path.exists(snap):
            os.unlink(snap)
            snap = None

    assert snap is None  # was cleaned up
    assert not os.path.exists(snap or ""), "temp file must not linger"


def test_snapshot_oserror_keeps_original_path(tmp_path):
    """If the source file is unreadable, we fall back to the original path (no crash)."""
    missing_path = str(tmp_path / "nonexistent.png")

    _snap: str | None = None
    result_path = missing_path  # default — stays unchanged on error
    try:
        with open(missing_path, "rb") as fh:
            raw = fh.read()
        fd, _snap = tempfile.mkstemp(suffix=".png")
        os.write(fd, raw)
        os.close(fd)
        result_path = _snap
    except OSError:
        pass  # mirrors api.py: keep original path, let downstream report the error

    # No crash, original path preserved
    assert result_path == missing_path
    assert _snap is None  # no temp file left open
