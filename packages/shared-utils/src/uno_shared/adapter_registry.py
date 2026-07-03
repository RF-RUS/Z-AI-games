"""Adapter registry — dynamic lookup of adapter implementations by type.

The orchestrator uses the registry to get the correct adapter client
without knowing about concrete adapter types.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from uno_shared.adapter_protocol import (
    AdapterRetryPolicy,
    GenericActionRequest,
    GenericActionResult,
    GenericAttachRequest,
    GenericAttachResponse,
    GenericEvidenceBundle,
)
from uno_shared.logging import get_logger

logger = get_logger("adapter_registry")


def _service_url(service: str) -> str:
    port_map = {
        "adapter-web": 8104,
        "adapter-windows": 8105,
    }
    port = port_map.get(service, 8099)
    host = os.getenv("UNO_SERVICE_HOST", "127.0.0.1")
    return f"http://{host}:{port}"


class GenericAdapterClient:
    """HTTP client that implements AdapterProtocol for any adapter service.

    Translates generic requests into adapter-specific HTTP calls by
    mapping fields to the expected endpoint format.
    """

    def __init__(
        self,
        adapter_type: str,
        base_url: str,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.adapter_type = adapter_type
        self.base_url = base_url
        self.timeout = timeout
        # Optional ASGI (or custom) transport. When set, all HTTP calls route
        # through it instead of the network — enables fully in-process runs
        # (e.g. autonomous mock sessions) without standing up the services.
        self._transport = transport

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout if timeout is not None else self.timeout,
            transport=self._transport,
        )

    def get_retry_policy(self) -> AdapterRetryPolicy:
        """Return the retry/recovery policy for this adapter type.

        This replaces hardcoded adapter-type branching in the orchestrator.
        Each adapter type returns its own policy that drives retry behavior,
        fallback decisions, and recovery semantics.
        """
        if self.adapter_type in ("web", "mock"):
            return AdapterRetryPolicy(
                max_retries=0,
                retry_on_transient=False,
                fallback_to_mock=False,
                fallback_to_manual=True,
                supports_launch_retry=False,
                classify_all_permanent=True,
                requires_warmup=True,
            )
        if self.adapter_type == "windows":
            return AdapterRetryPolicy(
                max_retries=3,
                retry_on_transient=True,
                fallback_to_mock=True,
                fallback_to_manual=True,
                supports_launch_retry=True,
                classify_all_permanent=False,
            )
        return AdapterRetryPolicy()

    async def attach(self, request: GenericAttachRequest) -> GenericAttachResponse:
        body = self._build_attach_body(request)
        timeout = self.timeout
        if self.adapter_type == "web" and request.extra.get("mode") == "playwright":
            timeout = 120.0
        async with self._client(timeout) as client:
            r = await client.post(f"{self.base_url}/attach", json=body)
            r.raise_for_status()
            data = r.json()
        return GenericAttachResponse(
            adapter_id=data.get("adapter_id"),
            session_id=data.get("session_id", request.session_id),
            attached=data.get("attached", False),
            message=data.get("message", ""),
            extra=data,
        )

    async def detach(self, adapter_id: str) -> None:
        async with self._client() as client:
            await client.post(f"{self.base_url}/adapters/{adapter_id}/detach")

    async def capture_evidence(
        self, adapter_id: str, correlation_id: str | None = None
    ) -> GenericEvidenceBundle:
        async with self._client() as client:
            params = {}
            if correlation_id:
                params["correlation_id"] = correlation_id
            r = await client.get(
                f"{self.base_url}/adapters/{adapter_id}/evidence", params=params
            )
            r.raise_for_status()
            data = r.json()
        return self._parse_evidence_response(adapter_id, data)

    async def execute_action(
        self,
        adapter_id: str,
        action: GenericActionRequest,
        correlation_id: str | None = None,
    ) -> GenericActionResult:
        body = self._build_action_body(action)
        async with self._client() as client:
            params = {}
            if correlation_id:
                params["correlation_id"] = correlation_id
            r = await client.post(
                f"{self.base_url}/adapters/{adapter_id}/actions",
                params=params,
                json=body,
            )
            r.raise_for_status()
            data = r.json()
        return GenericActionResult(
            success=data.get("success", False),
            action_type=data.get("action_type", action.action_type),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0),
            screenshot_path=data.get("screenshot_path"),
            extra=data,
        )

    async def list_profiles(self) -> list[dict[str, Any]]:
        async with self._client() as client:
            r = await client.get(f"{self.base_url}/profiles")
            r.raise_for_status()
            return r.json()

    async def load_profile(self, profile_id: str) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get(f"{self.base_url}/profiles/{profile_id}")
            r.raise_for_status()
            return r.json()

    def map_action(
        self,
        action_type: str,
        profile_id: str = "local-mock-uno",
        card_color: str | None = None,
        card_value: str | None = None,
        player_id: str | None = None,
        hand_cards: list[dict] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> GenericActionRequest:
        """Map a domain action to an adapter-specific GenericActionRequest.

        This is the single entry point for action translation. The flow
        controller calls this instead of adapter-specific mapping functions.

        When `payload` is provided, it contains the full game action payload
        (game-specific fields like card, position, etc.) and is passed through
        to the adapter's action mapping via `extra`.
        """
        extra_from_payload = payload if payload else {}
        if self.adapter_type in ("web", "mock"):
            return self._map_action_web(
                action_type, profile_id,
                card_color=card_color, card_value=card_value, hand_cards=hand_cards,
                extra=extra_from_payload,
            )
        if self.adapter_type == "windows":
            return self._map_action_windows(action_type, extra=extra_from_payload)
        return GenericActionRequest(
            action_type=action_type,
            domain_action=action_type,
            extra=extra_from_payload,
        )

    def _map_action_web(
        self, action_type: str, profile_id: str, card_color: str | None = None,
        card_value: str | None = None, hand_cards: list[dict] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> GenericActionRequest:
        """Web adapter action mapping — profile-driven selectors.

        UNO-specific card→slot logic is here for backward compatibility,
        but new games should use the payload/extra path instead.
        """
        base_extra = dict(extra) if extra else {}
        if profile_id == "scuffed-uno-web":
            if action_type == "play_card":
                slot_index = None
                if hand_cards:
                    slot_index = _find_card_slot_by_identity(hand_cards, card_color, card_value)
                if slot_index is None:
                    slot_index = _card_color_to_slot(card_color)
                return GenericActionRequest(
                    action_type="click_coordinate",
                    selector_key=f"hand_slot_{slot_index}",
                    domain_action=action_type,
                    extra={
                        **base_extra,
                        "coordinate_reference": "canvas",
                        "card_color": card_color,
                        "card_value": card_value,
                        "slot_index": slot_index,
                        "matched_by": "identity" if (hand_cards and slot_index is not None and _find_card_slot_by_identity(hand_cards, card_color, card_value) is not None) else "color_fallback",
                    },
                )
            if action_type == "draw_card":
                return GenericActionRequest(
                    action_type="click_coordinate",
                    selector_key="draw",
                    domain_action=action_type,
                    extra={**base_extra, "coordinate_reference": "canvas"},
                )
        if action_type == "draw_card":
            selector = (
                "#deck" if profile_id == "real-unoh-web"
                else "[data-testid='btn-draw']"
            )
            return GenericActionRequest(
                action_type="click",
                selector=selector,
                domain_action=action_type,
                extra=base_extra,
            )
        if action_type == "play_card":
            selector = (
                "#player-hand .card.playable"
                if profile_id == "real-unoh-web"
                else "[data-testid='btn-play-red5']"
            )
            return GenericActionRequest(
                action_type="click",
                selector=selector,
                domain_action=action_type,
                extra=base_extra,
            )
        return GenericActionRequest(
            action_type="click",
            selector="[data-action='draw']",
            domain_action=action_type,
            extra=base_extra,
        )

    def _map_action_windows(self, action_type: str, extra: dict[str, Any] | None = None) -> GenericActionRequest:
        """Windows adapter action mapping — UIA selector keys with coordinate fallback."""
        base_extra = dict(extra) if extra else {}
        selector_key = "draw"
        if action_type == "play_card":
            selector_key = "play_red_five"
        return GenericActionRequest(
            action_type="click_input",
            selector_key=selector_key,
            domain_action=action_type,
            extra={
                **base_extra,
                "capture_screenshots": True,
                "min_confidence": 0.55,
                "allow_coordinate_fallback": True,
            },
        )

    def _build_attach_body(self, request: GenericAttachRequest) -> dict[str, Any]:
        if self.adapter_type in ("web", "mock"):
            body = {
                "session_id": request.session_id,
                "profile_id": request.profile_id,
                "url": request.target_url,
                "mode": request.extra.get("mode", "mock" if self.adapter_type == "mock" else "playwright"),
                "headless": request.extra.get("headless", True),
                "record_trace": request.extra.get("record_trace", False),
            }
            if request.extra.get("cdp_url"):
                body["cdp_url"] = request.extra["cdp_url"]
            return body
        if self.adapter_type == "windows":
            return {
                "session_id": request.session_id,
                "profile_id": request.profile_id,
                "window_title": request.window_title,
                "window_handle": request.window_handle,
                "window_pid": request.window_pid,
                "mode": request.extra.get("mode", "pywinauto"),
                "launch_test_target": request.launch_test_target,
                "capture_screenshots": request.extra.get("capture_screenshots", True),
                "attended_rpa": request.use_real_backend,
            }
        return {
            "session_id": request.session_id,
            "profile_id": request.profile_id,
        }

    def normalize_attach_request(
        self,
        session_id: str,
        profile_id: str,
        *,
        target_url: str | None = None,
        window_title: str | None = None,
        window_handle: int | None = None,
        window_pid: int | None = None,
        launch_test_target: bool = False,
        use_real_backend: bool = True,
        cdp_url: str | None = None,
    ) -> GenericAttachRequest:
        """Normalize raw attach intent into adapter-specific GenericAttachRequest.

        The orchestrator calls this instead of building the request itself.
        All adapter-specific normalization (launch logic, mode selection,
        trace flags) lives here.
        """
        if self.adapter_type in ("web", "mock"):
            return self._normalize_web_request(
                session_id, profile_id, target_url=target_url,
                launch_test_target=launch_test_target,
                cdp_url=cdp_url,
            )
        if self.adapter_type == "windows":
            return self._normalize_windows_request(
                session_id, profile_id,
                window_title=window_title, window_handle=window_handle,
                window_pid=window_pid, launch_test_target=launch_test_target,
                use_real_backend=use_real_backend,
            )
        return GenericAttachRequest(
            session_id=session_id, profile_id=profile_id,
            adapter_type=self.adapter_type,
        )

    def _normalize_web_request(
        self,
        session_id: str,
        profile_id: str,
        *,
        target_url: str | None = None,
        launch_test_target: bool = False,
        cdp_url: str | None = None,
    ) -> GenericAttachRequest:
        mode = "mock" if self.adapter_type == "mock" else "playwright"
        extra: dict = {
            "mode": mode,
            "record_trace": self.adapter_type != "mock",
            "capture_screenshots": True,
        }
        if cdp_url:
            extra["cdp_url"] = cdp_url
        return GenericAttachRequest(
            session_id=session_id,
            profile_id=profile_id,
            adapter_type=self.adapter_type,
            target_url=target_url,
            launch_test_target=launch_test_target,
            extra=extra,
        )

    def _normalize_windows_request(
        self,
        session_id: str,
        profile_id: str,
        *,
        window_title: str | None = None,
        window_handle: int | None = None,
        window_pid: int | None = None,
        launch_test_target: bool = False,
        use_real_backend: bool = True,
    ) -> GenericAttachRequest:
        computed_launch = (
            launch_test_target
            and profile_id == "local-mock-uno"
            and window_handle is None
        )
        return GenericAttachRequest(
            session_id=session_id,
            profile_id=profile_id,
            adapter_type="windows",
            window_title=window_title,
            window_handle=window_handle,
            window_pid=window_pid,
            launch_test_target=computed_launch,
            use_real_backend=use_real_backend,
            extra={
                "mode": "pywinauto" if use_real_backend else "mock",
                "record_trace": True,
                "capture_screenshots": True,
            },
        )

    def _build_action_body(self, action: GenericActionRequest) -> dict[str, Any]:
        if self.adapter_type in ("web", "mock"):
            return {
                "action_type": action.action_type,
                "selector": action.selector,
                "selector_key": action.selector_key,
                "domain_action": action.domain_action,
                "text": action.text,
                "key": action.key,
                "timeout_ms": action.timeout_ms,
            }
        if self.adapter_type == "windows":
            body = {
                "action_type": action.action_type,
                "selector_key": action.selector_key or action.selector or "default",
                "domain_action": action.domain_action,
                "capture_screenshots": True,
                "min_confidence": 0.55,
                "allow_coordinate_fallback": False,
            }
            body.update(action.extra)
            return body
        return action.model_dump(exclude_none=True)

    def _parse_evidence_response(
        self, adapter_id: str, data: dict[str, Any]
    ) -> GenericEvidenceBundle:
        dom = data.get("dom_evidence")
        ui = data.get("ui_evidence")
        screenshot = data.get("screenshot")
        screenshot_path = None
        if isinstance(screenshot, dict):
            screenshot_path = screenshot.get("path")
        elif isinstance(screenshot, str):
            screenshot_path = screenshot
        return GenericEvidenceBundle(
            adapter_id=adapter_id,
            session_id=data.get("session_id", ""),
            dom_evidence=dom,
            ui_evidence=ui,
            screenshot_path=screenshot_path,
            correlation_id=data.get("correlation_id"),
            extra=data,
        )


_COLOR_SLOT_MAP = {
    "red": 0, "blue": 1, "green": 2, "yellow": 3,
}


def _card_color_to_slot(color: str | None) -> int:
    """Map UNO card color to hand slot index for canvas coordinate targeting.

    Uses a fixed mapping: red=0, blue=1, green=2, yellow=3.
    For multi-card same-color hands, this picks the first slot.
    """
    if not color:
        return 0
    return _COLOR_SLOT_MAP.get(color.lower(), 0)


def _find_card_slot_by_identity(
    hand_cards: list[dict], card_color: str | None, card_value: str | None
) -> int | None:
    """Find the slot index for a specific card by color + number identity.

    hand_cards: list of {color, number, slot_index} from CV detection
    Returns slot_index if found, None otherwise.
    """
    if not hand_cards:
        return None
    for card in hand_cards:
        card_color_match = not card_color or card.get("color", "").lower() == card_color.lower()
        card_number_match = not card_value or str(card.get("number", "")) == str(card_value)
        if card_color_match and card_number_match:
            return card.get("slot_index")
    return None


class AdapterRegistry:
    """Registry of adapter implementations by adapter type.

    Usage:
        registry = AdapterRegistry()
        client = registry.get_client("web")
        response = await client.attach(request)
    """

    def __init__(self) -> None:
        self._clients: dict[str, GenericAdapterClient] = {}
        self._init_default_clients()

    def _init_default_clients(self) -> None:
        for adapter_type, service_name in [
            ("web", "adapter-web"),
            ("windows", "adapter-windows"),
            ("mock", "adapter-web"),
        ]:
            self._clients[adapter_type] = GenericAdapterClient(
                adapter_type=adapter_type,
                base_url=_service_url(service_name),
            )

    def get_client(self, adapter_type: str) -> GenericAdapterClient:
        if adapter_type not in self._clients:
            raise KeyError(f"no adapter registered for type: {adapter_type}")
        return self._clients[adapter_type]

    def get_retry_policy(self, adapter_type: str) -> AdapterRetryPolicy:
        """Return the retry/recovery policy for an adapter type."""
        return self.get_client(adapter_type).get_retry_policy()

    def register(
        self, adapter_type: str, client: GenericAdapterClient
    ) -> None:
        self._clients[adapter_type] = client

    def has_adapter(self, adapter_type: str) -> bool:
        return adapter_type in self._clients

    def supported_types(self) -> list[str]:
        return list(self._clients.keys())


_registry: AdapterRegistry | None = None


def get_adapter_registry() -> AdapterRegistry:
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
    return _registry


def set_adapter_registry(registry: AdapterRegistry) -> None:
    global _registry
    _registry = registry
