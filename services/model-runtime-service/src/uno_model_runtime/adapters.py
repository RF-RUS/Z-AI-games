"""Unified inference interface with pluggable runtime adapters."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from uno_schemas.model import InferenceRequest, InferenceResponse, RuntimeAdapter


class RuntimeAdapterBase(ABC):
  @abstractmethod
  async def infer(self, req: InferenceRequest) -> InferenceResponse: ...


class MockRuntime(RuntimeAdapterBase):
  async def infer(self, req: InferenceRequest) -> InferenceResponse:
    start = time.perf_counter()
    text = f"[mock] Response to: {req.prompt[:80]}"
    if req.image_base64:
      text += " (with image)"
    latency = int((time.perf_counter() - start) * 1000)
    return InferenceResponse(
      model_id=req.model_id,
      text=text,
      confidence=0.5,
      latency_ms=latency,
      correlation_id=req.correlation_id,
    )


class LlamaCppRuntime(RuntimeAdapterBase):
  """GGUF/llama.cpp adapter — loads when binary available."""

  async def infer(self, req: InferenceRequest) -> InferenceResponse:
    start = time.perf_counter()
    # Production: invoke llama.cpp server or python binding
    text = f"[llama.cpp stub] {req.prompt[:100]}"
    return InferenceResponse(
      model_id=req.model_id,
      text=text,
      confidence=0.6,
      latency_ms=int((time.perf_counter() - start) * 1000),
      correlation_id=req.correlation_id,
    )


class VllmRuntime(RuntimeAdapterBase):
  async def infer(self, req: InferenceRequest) -> InferenceResponse:
    start = time.perf_counter()
    text = f"[vLLM stub] {req.prompt[:100]}"
    return InferenceResponse(
      model_id=req.model_id,
      text=text,
      confidence=0.7,
      latency_ms=int((time.perf_counter() - start) * 1000),
      correlation_id=req.correlation_id,
    )


def get_runtime(adapter: RuntimeAdapter) -> RuntimeAdapterBase:
  return {
    RuntimeAdapter.MOCK: MockRuntime(),
    RuntimeAdapter.LLAMA_CPP: LlamaCppRuntime(),
    RuntimeAdapter.VLLM: VllmRuntime(),
  }[adapter]
