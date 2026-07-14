"""Action grounding protocol — "where do I click to perform action X?".

This is the seam that makes the agent game-agnostic. Perception answers *what*
is on screen (state); grounding answers *where* to click for a decided action.
The Windows/Web adapters stay dumb: they receive a click point and click it,
with no knowledge of cards, colours, or suits.

A GroundingProvider takes a decided action (e.g. choose_color=red) plus the
current screenshot and returns a click point in screenshot coordinates, or None
if it cannot ground the action. Providers are tried cheapest-first and the first
confident hit wins (graceful degradation):

    1. UIAGroundingProvider      — native windows, elements exist in the UIA tree
    2. TemplateGroundingProvider — OpenCV template/anchor match (per-game assets)
    3. VLMGroundingProvider      — Set-of-Marks over a VLM (any game, no assets)

New games plug in by supplying a profile (+ optional templates / vision model),
never by patching an adapter. Successful VLM hits should be cached as learned
zones so the next identical situation resolves via the cheap path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class GroundingRequest:
    """A decided action that needs a screen location to be executed."""

    action_type: str                 # "choose_color" | "play_card" | "draw" | ...
    screenshot_path: str             # path to the current frame (PNG)
    # Free-form action parameters the provider may need to disambiguate a target,
    # e.g. {"color": "red"} for choose_color or {"card": "red_5"} for play_card.
    # Kept opaque so new games add params without changing this contract.
    params: dict = field(default_factory=dict)
    game_type: str = "unknown"
    # Optional layout hints: learned zones, anchors, template refs, screen bounds.
    profile: dict | None = None


@dataclass
class GroundingResult:
    """Where to click for the requested action, in screenshot coordinates."""

    found: bool
    x: float | None = None           # screenshot-space X (adapter maps to screen)
    y: float | None = None           # screenshot-space Y
    confidence: float = 0.0          # 0-1
    method: str = "none"             # "uia" | "template" | "vlm" | "learned_zone"
    # Why this provider did/didn't ground the action — surfaced to the operator
    # and useful for deciding whether to fall through to the next provider.
    reason: str = ""
    metadata: dict = field(default_factory=dict)

    @classmethod
    def miss(cls, method: str, reason: str) -> GroundingResult:
        return cls(found=False, method=method, reason=reason)

    @classmethod
    def hit(
        cls, x: float, y: float, confidence: float, method: str, reason: str = "",
        **metadata: object,
    ) -> GroundingResult:
        return cls(
            found=True, x=x, y=y, confidence=confidence, method=method,
            reason=reason, metadata=dict(metadata),
        )


@runtime_checkable
class GroundingProvider(Protocol):
    """Protocol for action-grounding providers (UIA, template, VLM, ...)."""

    # Stable identifier for logs/metrics: "uia" | "template" | "vlm".
    method: str

    async def ground(self, req: GroundingRequest) -> GroundingResult:
        """Resolve a click point for the requested action.

        Return GroundingResult.miss(...) (not an exception) when the action
        cannot be grounded, so the resolver can fall through to the next
        provider. Raise only on genuinely unexpected failures.
        """
        ...


async def resolve_grounding(
    req: GroundingRequest,
    providers: list[GroundingProvider],
    *,
    min_confidence: float = 0.5,
) -> GroundingResult:
    """Try providers cheapest-first; first hit at or above min_confidence wins.

    Providers that miss or raise are skipped so a broken provider never blocks a
    working fallback. If nothing grounds the action, the last miss is returned so
    the caller can surface the most informative reason.
    """
    last: GroundingResult = GroundingResult.miss("none", "no providers configured")
    for provider in providers:
        try:
            result = await provider.ground(req)
        except Exception as exc:  # noqa: BLE001 — a bad provider must not block fallbacks
            last = GroundingResult.miss(provider.method, f"provider error: {exc}")
            continue
        if result.found and result.confidence >= min_confidence:
            return result
        last = result
    return last
