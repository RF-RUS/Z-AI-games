from fastapi import FastAPI
from uno_chat_response.generator import generate_reply
from uno_schemas.chat import ChatReply, ChatReplyRequest
from uno_shared.service_app import ServiceApp

svc = ServiceApp("chat-response-service", description="Safe chat reply generation")
app: FastAPI = svc.create_app()


@app.post("/reply", response_model=ChatReply, tags=["chat"])
async def reply(req: ChatReplyRequest) -> ChatReply:
  return await generate_reply(
    req,
    game_type=req.intent.trigger_message.sender if req.intent else "unknown",
    use_model=req.use_model,
  )


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_chat_response.api:app", host="127.0.0.1", port=SERVICE_PORTS["chat-response-service"])
