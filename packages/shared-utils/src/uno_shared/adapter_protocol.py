"""Protocol for GUI adapter implementations.

Defines the unified interface that all adapters (web, windows, future)
must implement. The orchestrator depends only on this protocol, never
on concrete adapter types.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class GenericAttachRequest(BaseModel):
    """Adapter-agnostic attach request. Adapters interpret fields as needed."""

    session_id: str
    profile_id: str
    adapter_type: str
    target_url: str | None = None
    window_title: str | None = None
    window_handle: int | None = None
    window_pid: int | None = None
    launch_test_target: bool = False
    use_real_backend: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)


class GenericAttachResponse(BaseModel):
    """Adapter-agnostic attach response."""

    adapter_id: str | None = None
    session_id: str
    attached: bool
    message: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class GenericEvidenceBundle(BaseModel):
    """Unified evidence bundle returned by all adapters.

    Contains optional dom_evidence (for web adapters) and
    ui_evidence (for windows adapters). The flow controller
    passes whichever is non-None to the perception service.
    """

    adapter_id: str
    session_id: str
    dom_evidence: dict[str, Any] | None = None
    ui_evidence: dict[str, Any] | None = None
    screenshot_path: str | None = None
    correlation_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class GenericActionRequest(BaseModel):
    """Adapter-agnostic action execution request."""

    action_type: str
    selector: str | None = None
    selector_key: str | None = None
    domain_action: str | None = None
    text: str | None = None
    key: str | None = None
    timeout_ms: int = 10000
    extra: dict[str, Any] = Field(default_factory=dict)


class GenericActionResult(BaseModel):
    """Adapter-agnostic action execution result."""

    success: bool
    action_type: str
    error: str | None = None
    duration_ms: int = 0
    screenshot_path: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AdapterRetryPolicy(BaseModel):
    """Retry/recovery policy for an adapter type.

    This model replaces hardcoded adapter-type branching in the
    orchestrator and recovery logic. Each adapter type provides
    its own policy that drives retry behavior, fallback decisions,
    and recovery semantics.
    """

    max_retries: int = 0
    retry_on_transient: bool = False
    fallback_to_mock: bool = False
    fallback_to_manual: bool = True
    supports_launch_retry: bool = False
    classify_all_permanent: bool = False
    requires_warmup: bool = False


class AdapterProtocol(Protocol):
    """Unified interface for all GUI adapters.

    Each adapter service (adapter-web, adapter-windows, future adapters)
    implements this protocol via a GenericAdapterClient that wraps HTTP calls.
    """

    adapter_type: str

    async def attach(self, request: GenericAttachRequest) -> GenericAttachResponse:
        """Attach to a GUI target."""
        ...

    async def detach(self, adapter_id: str) -> None:
        """Detach from a GUI target."""
        ...

    async def capture_evidence(
        self, adapter_id: str, correlation_id: str | None = None
    ) -> GenericEvidenceBundle:
        """Capture current GUI state as evidence."""
        ...

    async def execute_action(
        self,
        adapter_id: str,
        action: GenericActionRequest,
        correlation_id: str | None = None,
    ) -> GenericActionResult:
        """Execute an action on the GUI."""
        ...

    async def list_profiles(self) -> list[dict[str, Any]]:
        """List available profiles for this adapter type."""
        ...

    async def load_profile(self, profile_id: str) -> dict[str, Any]:
        """Load a specific profile."""
        ...
