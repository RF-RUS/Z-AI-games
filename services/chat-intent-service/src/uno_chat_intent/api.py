from fastapi import FastAPI
from pydantic import BaseModel
from uno_chat_intent.detector import detect_intent, parse_chat_messages
from uno_schemas.chat import ChatIntent, ChatMessage
from uno_shared.service_app import ServiceApp

svc = ServiceApp("chat-intent-service", description="Chat intent detection")
app: FastAPI = svc.create_app()


class IntentRequest(BaseModel):
  messages: list[ChatMessage] = []
  raw_lines: list[str] | None = None
  use_model: bool = False
  game_type: str = "unknown"
  model_profile_id: str | None = None


@app.post("/detect", response_model=ChatIntent | None, tags=["chat"])
async def detect(req: IntentRequest) -> ChatIntent | None:
  messages = req.messages or parse_chat_messages(req.raw_lines or [])
  return await detect_intent(
    messages,
    use_model=req.use_model,
    game_type=req.game_type,
    model_profile_id=req.model_profile_id,
  )


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_chat_intent.api:app", host="127.0.0.1", port=SERVICE_PORTS["chat-intent-service"])
