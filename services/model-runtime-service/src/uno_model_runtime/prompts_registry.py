"""Versioned prompt registry."""

from __future__ import annotations

from pathlib import Path

from uno_schemas.model import ModelUseCase
from uno_schemas.prompts import PromptProfile, PromptResolution

PROMPTS_DIR = Path(__file__).resolve().parents[4] / "prompts"


def _prompts_root() -> Path:
  # services/model-runtime-service/src/uno_model_runtime/prompts_registry.py -> repo root
  return Path(__file__).resolve().parents[4] / "prompts"


def list_prompts() -> list[PromptProfile]:
  root = _prompts_root()
  profiles: list[PromptProfile] = []
  if not root.exists():
    return profiles
  for path in sorted(root.rglob("*.json")):
    profiles.append(PromptProfile.model_validate_json(path.read_text(encoding="utf-8")))
  return profiles


def render_template(template: str, variables: dict[str, str]) -> str:
  rendered = template
  for key, value in variables.items():
    rendered = rendered.replace(f"{{{key}}}", value)
  return rendered


def resolve_prompt(
  use_case: ModelUseCase,
  variables: dict[str, str],
  prompt_id: str | None = None,
  version: str | None = None,
) -> PromptResolution:
  candidates = [p for p in list_prompts() if p.use_case == use_case and p.active]
  if prompt_id:
    candidates = [p for p in candidates if p.prompt_id == prompt_id]
  if version:
    candidates = [p for p in candidates if p.version == version]
  if not candidates:
    raise FileNotFoundError(f"no active prompt for {use_case.value}")
  profile = sorted(candidates, key=lambda p: p.version, reverse=True)[0]
  rendered = render_template(profile.template, {k: variables.get(k, "") for k in _extract_vars(profile.template)})
  return PromptResolution(
    prompt_id=profile.prompt_id,
    version=profile.version,
    use_case=use_case,
    rendered_prompt=rendered,
    expected_output_schema=profile.expected_output_schema,
  )


def _extract_vars(template: str) -> list[str]:
  import re
  return re.findall(r"\{(\w+)\}", template)
