"""Model registry and runtime domain models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from uno_schemas.ids import Confidence, ModelId, TimestampMs


class ModelModality(StrEnum):
  TEXT = "text"
  VISION = "vision"
  MULTIMODAL = "multimodal"


class RuntimeAdapter(StrEnum):
  LLAMA_CPP = "llama_cpp"
  VLLM = "vllm"
  MOCK = "mock"


class ModelProviderType(StrEnum):
  MOCK = "mock"
  LLAMA_CPP_OPENAI = "llama_cpp_openai"
  VLLM_OPENAI = "vllm_openai"


class ModelUseCase(StrEnum):
  CHAT_INTENT = "chat_intent"
  CHAT_REPLY = "chat_reply"
  PERCEPTION_DISPUTE = "perception_dispute"
  EXPLANATION = "explanation"
  POLICY_ADVICE = "policy_advice"
  BENCHMARK_ONLY = "benchmark_only"


class ModelCapability(StrEnum):
  TEXT_GENERATION = "text_generation"
  VISION_UNDERSTANDING = "vision_understanding"
  ACTION_RANKING = "action_ranking"
  CHAT_REPLY = "chat_reply"


class ModelManifest(BaseModel):
  model_id: ModelId
  display_name: str
  source_repo: str
  revision: str = "main"
  files: list[str] = Field(default_factory=list)
  modality: ModelModality
  runtime: RuntimeAdapter
  provider: ModelProviderType = ModelProviderType.MOCK
  capabilities: list[ModelCapability] = Field(default_factory=list)
  context_length: int = 4096
  quantization: str | None = None
  local_path: str | None = None
  download_url: HttpUrl | str | None = None
  enabled: bool = False
  metadata: dict[str, str] = Field(default_factory=dict)


class ModelProfile(BaseModel):
  """Extended registry profile with routing and provider config."""
  profile_id: ModelId
  display_name: str
  alias: str | None = None
  provider: ModelProviderType = ModelProviderType.MOCK
  base_url: str | None = None
  model_name: str | None = None
  api_key_env: str = "OPENAI_API_KEY"
  enabled: bool = True
  capabilities: list[ModelCapability] = Field(default_factory=list)
  use_cases: list[ModelUseCase] = Field(default_factory=list)
  priority: int = Field(default=100, ge=0)
  max_tokens_default: int = 256
  temperature_default: float = 0.2
  timeout_seconds: float = 30.0
  supports_json_mode: bool = False
  supports_multimodal: bool = False
  safety_limits: dict[str, str] = Field(default_factory=dict)
  metadata: dict[str, str] = Field(default_factory=dict)


class ModelRouteSelection(BaseModel):
  profile_id: ModelId
  provider: ModelProviderType
  base_url: str | None = None
  model_name: str | None = None
  use_case: ModelUseCase
  reason: str = ""


class ModelProviderHealth(BaseModel):
  provider: ModelProviderType
  healthy: bool
  latency_ms: int | None = None
  model_ids: list[str] = Field(default_factory=list)
  error: str | None = None


class ModelInvocationContext(BaseModel):
  use_case: ModelUseCase
  correlation_id: str
  session_id: str | None = None
  replay_id: str | None = None
  benchmark_run_id: str | None = None


class ModelInvocationRequest(BaseModel):
  context: ModelInvocationContext
  profile_id: ModelId | None = None
  prompt_id: str | None = None
  prompt_version: str | None = None
  variables: dict[str, str] = Field(default_factory=dict)
  prompt: str | None = None
  max_tokens: int = 256
  temperature: float = 0.2
  expect_json: bool = False


class StructuredModelOutput(BaseModel):
  raw: str
  parsed: dict[str, Any] | None = None
  parse_success: bool = False
  warnings: list[str] = Field(default_factory=list)


class ModelInvocationResponse(BaseModel):
  profile_id: ModelId
  provider: ModelProviderType
  prompt_id: str | None = None
  prompt_version: str | None = None
  text: str
  structured: StructuredModelOutput | None = None
  confidence: Confidence = 0.7
  latency_ms: int = Field(ge=0)
  correlation_id: str
  usage: dict[str, int] = Field(default_factory=dict)
  fallback_used: bool = False
  error: str | None = None


class ModelInstallRequest(BaseModel):
  model_id: ModelId
  source: str = "huggingface"
  force: bool = False


class ModelRuntimeSpec(BaseModel):
  model_id: ModelId
  runtime: RuntimeAdapter
  gpu_layers: int = 0
  threads: int = 4
  max_tokens: int = 512
  temperature: float = Field(default=0.3, ge=0.0, le=2.0)


class InferenceRequest(BaseModel):
  model_id: ModelId
  prompt: str
  image_base64: str | None = None
  max_tokens: int = 256
  temperature: float = 0.3
  correlation_id: str


class InferenceResponse(BaseModel):
  model_id: ModelId
  text: str
  confidence: Confidence = 0.7
  latency_ms: int = Field(ge=0)
  correlation_id: str


class BenchmarkCase(BaseModel):
  case_id: str
  use_case: ModelUseCase
  input: dict[str, Any]
  expected: dict[str, Any] = Field(default_factory=dict)
  tags: list[str] = Field(default_factory=list)


class BenchmarkRunRequest(BaseModel):
  dataset: str
  profile_id: ModelId | None = None
  prompt_id: str | None = None
  provider_override: ModelProviderType | None = None


class BenchmarkRun(BaseModel):
  run_id: str
  model_id: ModelId
  dataset: str
  prompt_id: str | None = None
  prompt_version: str | None = None
  provider: ModelProviderType
  started_at_ms: TimestampMs


class BenchmarkCaseResult(BaseModel):
  case_id: str
  success: bool
  score: float
  latency_ms: int
  parse_success: bool = False
  exact_match: bool = False
  error: str | None = None


class BenchmarkResult(BaseModel):
  run_id: str
  model_id: ModelId
  dataset: str
  prompt_id: str | None = None
  prompt_version: str | None = None
  provider: ModelProviderType
  score: float
  latency_p50_ms: float
  latency_p95_ms: float
  samples: int
  success_rate: float = 0.0
  parse_success_rate: float = 0.0
  case_results: list[BenchmarkCaseResult] = Field(default_factory=list)
  metadata: dict[str, str] = Field(default_factory=dict)
