from fastapi import FastAPI
from uno_decision.policy import decide
from uno_schemas.decision import DecisionRequest, DecisionResult
from uno_shared.service_app import ServiceApp

svc = ServiceApp("decision-service", description="Legal-action-only decision policies")
app: FastAPI = svc.create_app()


@app.post("/decide", response_model=DecisionResult, tags=["decision"])
async def decide_action(req: DecisionRequest) -> DecisionResult:
  return await decide(req)


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_decision.api:app", host="127.0.0.1", port=SERVICE_PORTS["decision-service"])
