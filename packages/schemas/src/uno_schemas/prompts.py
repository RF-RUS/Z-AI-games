"""Prompt registry and versioning."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from uno_schemas.model import ModelUseCase


class PromptProfile(BaseModel):
  prompt_id: str
  version: str
  use_case: ModelUseCase
  template: str
  expected_output_schema: dict[str, Any] = Field(default_factory=dict)
  safety_notes: str = ""
  compatible_model_families: list[str] = Field(default_factory=list)
  active: bool = True


class PromptResolution(BaseModel):
  prompt_id: str
  version: str
  use_case: ModelUseCase
  rendered_prompt: str
  expected_output_schema: dict[str, Any] = Field(default_factory=dict)
