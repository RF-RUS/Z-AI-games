from collections import deque
from datetime import UTC, datetime

from fastapi import FastAPI
from pydantic import BaseModel, Field
from uno_shared.service_app import ServiceApp

_log_buffer: deque = deque(maxlen=1000)
_trace_buffer: deque = deque(maxlen=500)

svc = ServiceApp("observability-service", description="Logs, traces, metrics")
app: FastAPI = svc.create_app()


class LogEntry(BaseModel):
  level: str
  message: str
  service: str
  correlation_id: str | None = None
  timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
  extra: dict = Field(default_factory=dict)


@app.post("/logs", tags=["observability"])
async def ingest_log(entry: LogEntry) -> dict:
  _log_buffer.append(entry)
  return {"stored": True}


@app.get("/logs", response_model=list[LogEntry], tags=["observability"])
async def get_logs(limit: int = 50, correlation_id: str | None = None) -> list[LogEntry]:
  logs = list(_log_buffer)
  if correlation_id:
    logs = [l for l in logs if l.correlation_id == correlation_id]
  return logs[-limit:]


@app.get("/metrics", tags=["observability"])
async def metrics() -> dict:
  return {
    "logs_count": len(_log_buffer),
    "traces_count": len(_trace_buffer),
  }


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_observability.api:app", host="127.0.0.1", port=SERVICE_PORTS["observability-service"])
