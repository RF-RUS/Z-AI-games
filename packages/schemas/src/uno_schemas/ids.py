"""Strongly typed identifier primitives."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

GameId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
SessionId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
AdapterId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
ModelId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
ReplayId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
ObservationId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
CorrelationId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
EventId = Annotated[str, StringConstraints(min_length=1, max_length=64)]

TimestampMs = Annotated[int, Field(ge=0)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
