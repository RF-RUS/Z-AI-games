import os
from collections import deque
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field
from uno_shared.service_app import ServiceApp

_log_buffer: deque = deque(maxlen=1000)
_trace_buffer: deque = deque(maxlen=500)
# Aggregated step metrics reported by every service via /metrics/report
_step_counts: dict[str, int] = {}
_step_latency_ms_sum: dict[tuple[str, str], float] = {}
_step_calls: dict[tuple[str, str], int] = {}
_recent_reports: deque = deque(maxlen=500)

svc = ServiceApp("observability-service", description="Logs, traces, metrics")
app: FastAPI = svc.create_app()

class LogEntry(BaseModel):
  level: str
  message: str
  service: str
  correlation_id: str | None = None
  timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
  extra: dict = Field(default_factory=dict)

class StepMetricReport(BaseModel):
  service: str
  path: str
  status: int
  latency_ms: float
  correlation_id: str | None = None

@app.post("/logs", tags=["observability"])
async def ingest_log(entry: LogEntry) -> dict:
  _log_buffer.append(entry)
  return {"stored": True}

@app.get("/logs", response_model=list[LogEntry], tags=["observability"])
async def get_logs(limit: int = 50, correlation_id: str | None = None) -> list[LogEntry]:
  logs = list(_log_buffer)
  if correlation_id:
    logs = [entry for entry in logs if entry.correlation_id == correlation_id]
  return logs[-limit:]

@app.post("/metrics/report", tags=["observability"])
async def report_metric(report: StepMetricReport) -> dict:
  key = (report.service, report.path)
  bucket = f"{report.status // 100}xx"
  _step_counts[bucket] = _step_counts.get(bucket, 0) + 1
  _step_latency_ms_sum[key] = _step_latency_ms_sum.get(key, 0.0) + report.latency_ms
  _step_calls[key] = _step_calls.get(key, 0) + 1
  _recent_reports.append({"ts": datetime.now(UTC).isoformat(), **report.model_dump()})
  return {"stored": True}

@app.get("/traces/{correlation_id}", tags=["observability"])
async def get_trace(correlation_id: str) -> dict:
  """Cross-service view of one pipeline run.

  Joins the log lines tagged with this correlation id (every service binds the
  inbound X-Trace-Id into its structured logs, so a full observe→record cycle is
  reconstructable from the collected entries) plus any reported steps.
  """
  logs = [e.model_dump(mode="json") for e in _log_buffer if e.correlation_id == correlation_id]
  steps = [r for r in _recent_reports if r.get("correlation_id") == correlation_id]
  return {"correlation_id": correlation_id, "logs": logs, "steps": steps}

# NOTE: GET /metrics on THIS app is the standard per-service snapshot provided by
# ServiceApp (same shape as every other service — consistency first). The platform
# WIDE aggregate built from /metrics/report entries lives at /metrics/summary.
@app.get("/metrics/summary", tags=["observability"])
async def metrics_summary() -> dict:
  avg_by_service: dict[str, dict[str, Any]] = {}
  for (service, path), total_ms in _step_latency_ms_sum.items():
    calls = _step_calls.get((service, path), 0) or 1
    entry = avg_by_service.setdefault(service, {})
    entry[path] = {
      "calls": _step_calls.get((service, path), 0),
      "avg_latency_ms": round(total_ms / calls, 1),
    }
  return {
    "logs_count": len(_log_buffer),
    "traces_count": len(_trace_buffer),
    "total_reported_steps": sum(_step_counts.values()),
    "by_status": dict(_step_counts),
    "latency_by_service": avg_by_service,
    "recent": list(_recent_reports)[-50:],
  }

def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_observability.api:app", host=os.getenv("UNO_UVICORN_HOST", "127.0.0.1"), port=SERVICE_PORTS["observability-service"])

