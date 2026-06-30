from fastapi import FastAPI
from pydantic import BaseModel, Field
from uno_policy.guard import validate_chat_reply, validate_decision
from uno_schemas.chat import ChatPolicyResult, ChatReply
from uno_schemas.decision import DecisionResult, PolicyViolation
from uno_schemas.game import LegalAction
from uno_shared.service_app import ServiceApp

svc = ServiceApp("policy-guard", description="Hard safety validation layer")
app: FastAPI = svc.create_app()


class GuardDecisionRequest(BaseModel):
  decision: DecisionResult
  legal_actions: list[LegalAction]
  min_confidence: float = Field(default=0.3, ge=0.0, le=1.0)


class GuardDecisionResponse(BaseModel):
  allowed: bool
  violation: PolicyViolation | None = None


@app.post("/guard/decision", response_model=GuardDecisionResponse, tags=["guard"])
async def guard_decision(req: GuardDecisionRequest) -> GuardDecisionResponse:
  allowed, violation = validate_decision(req.decision, req.legal_actions, req.min_confidence)
  return GuardDecisionResponse(allowed=allowed, violation=violation)


@app.post("/guard/chat", response_model=ChatPolicyResult, tags=["guard"])
async def guard_chat(reply: ChatReply) -> ChatPolicyResult:
  allowed, violations = validate_chat_reply(reply, reply.correlation_id)
  return ChatPolicyResult(allowed=allowed, reply=reply if allowed else None, violations=violations, correlation_id=reply.correlation_id)


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_policy.api:app", host="127.0.0.1", port=SERVICE_PORTS["policy-guard"])
