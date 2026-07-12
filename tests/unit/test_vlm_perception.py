"""Tests for the VLM perception path (#10, D6).

Covers the two things that are verifiable without a real vision model or a
Windows host: (1) the normalizer maps a VLM board dict into the canonical
game_state shape the merger + operator panel consume, and (2) the merger treats
a VLM board as PRIMARY — folding its cards into game_state and NOT letting the
per-game heuristic overwrite them. The real model is swapped in later via config
(VLM_PERCEPTION=1 + a vision profile); this pins the wiring around it.
"""

from __future__ import annotations

from pathlib import Path

from uno_perception.merger import build_observation
from uno_perception.vlm_provider import _normalize_board
from uno_schemas.perception import ScreenshotFrame, VisionInference

FIXture = Path(__file__).resolve().parents[1] / "fixtures" / "uno_desktop" / "ubisoft_hand3.jpeg"


# --- _normalize_board -------------------------------------------------------

def test_normalize_board_maps_to_canonical_shape():
    raw = {
        "screen_state": "in_game",
        "whose_turn": "self",
        "top_card": {"color": "Red", "value": "6"},
        "hand_cards": [
            {"color": "red", "value": "6"},
            {"color": "green", "value": "reverse"},
            {"color": "yellow", "number": "reverse"},  # 'number' alias
        ],
        "confidence": 0.8,
    }
    out = _normalize_board(raw)
    assert out is not None
    assert out["screen_type"] == "in_game" and out["whose_turn"] == "self"
    assert out["top_card"] == {"color": "red", "value": "6"}  # lowercased
    assert out["hand_count"] == 3
    assert out["hand_cards"][2] == {"color": "yellow", "value": "reverse"}
    assert out["source"] == "vlm"


def test_normalize_board_empty_returns_none():
    assert _normalize_board({}) is None
    assert _normalize_board({"hand_cards": []}) is None
    assert _normalize_board("not a dict") is None


def test_normalize_board_colour_only_ok():
    out = _normalize_board({"hand_cards": [{"color": "blue", "value": ""}]})
    assert out is not None and out["hand_cards"] == [{"color": "blue", "value": ""}]


# --- merger treats VLM board as primary -------------------------------------

def _vlm(structured: dict, conf: float = 0.8) -> VisionInference:
    return VisionInference(model_id="test-vlm", raw_output="{}", structured=structured, confidence=conf)


def test_merger_uses_vlm_board_as_primary():
    board = _normalize_board({
        "screen_state": "in_game", "whose_turn": "self",
        "top_card": {"color": "red", "value": "6"},
        "hand_cards": [{"color": "red", "value": "6"}, {"color": "green", "value": "reverse"}],
        "confidence": 0.8,
    })
    obs = build_observation("s1", vlm=_vlm(board), game_type="uno")
    gs = obs.game_state or {}
    assert gs.get("hand_count") == 2
    assert gs.get("top_card") == {"color": "red", "value": "6"}
    assert gs.get("recognition_method") == "vlm"
    assert gs.get("cv_build") == "v3"
    assert obs.confidence.game_state > 0.0  # so flow won't re-classify not_in_game


def test_merger_vlm_board_survives_screenshot_present():
    """A real screenshot is attached too — the heuristic must NOT clobber VLM cards."""
    board = _normalize_board({
        "screen_state": "in_game",
        "top_card": {"color": "yellow", "value": "reverse"},
        "hand_cards": [{"color": "red", "value": "6"}, {"color": "green", "value": "reverse"},
                       {"color": "yellow", "value": "reverse"}],
        "confidence": 0.82,
    })
    shot = ScreenshotFrame(
        frame_id="f1", session_id="s1", width=1296, height=759,
        path=str(FIXture) if FIXture.exists() else None, captured_at_ms=1,
    )
    obs = build_observation("s1", vlm=_vlm(board), screenshot=shot, game_type="uno")
    gs = obs.game_state or {}
    # VLM's 3 cards survive; heuristic did not overwrite hand_cards/top_card.
    assert gs.get("hand_count") == 3
    assert gs.get("top_card") == {"color": "yellow", "value": "reverse"}
    assert gs.get("recognition_method") == "vlm"
