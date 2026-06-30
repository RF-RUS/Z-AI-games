"""FastAPI surface for uno-core."""

from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field
from uno_schemas.game import DomainEvent, LegalAction, ReplayEnvelope
from uno_shared.service_app import ServiceApp

from uno_core.reducer import apply_action, to_public_table_state
from uno_core.rules import generate_legal_actions, validate_action
from uno_core.state import GameState, create_initial_state

# In-memory game sessions for local dev
_games: dict[str, GameState] = {}
_event_log: dict[str, list[DomainEvent]] = {}

svc = ServiceApp("uno-core", description="Canonical UNO rules engine")
app = svc.create_app()


class NewGameRequest(BaseModel):
  player_names: list[str] = Field(min_length=2, max_length=10)
  seed: int | None = None


class NewGameResponse(BaseModel):
  game_id: str
  players: list[dict]
  public_state: dict


class LegalActionsResponse(BaseModel):
  game_id: str
  actions: list[LegalAction]


class ApplyActionRequest(BaseModel):
  action: LegalAction
  session_id: str | None = None


class ApplyActionResponse(BaseModel):
  success: bool
  events: list[DomainEvent]
  public_state: dict
  winner_id: str | None = None


@app.post("/games", response_model=NewGameResponse, tags=["games"])
async def create_game(req: NewGameRequest) -> NewGameResponse:
  game_id = str(uuid4())
  state = create_initial_state(game_id, req.player_names, req.seed)
  _games[game_id] = state
  _event_log[game_id] = []
  return NewGameResponse(
    game_id=game_id,
    players=[p.model_dump() for p in state.players],
    public_state=to_public_table_state(state).model_dump(),
  )


@app.get("/games/{game_id}/legal-actions", response_model=LegalActionsResponse, tags=["games"])
async def legal_actions(game_id: str) -> LegalActionsResponse:
  state = _get_game(game_id)
  return LegalActionsResponse(game_id=game_id, actions=generate_legal_actions(state))


@app.post("/games/{game_id}/actions", response_model=ApplyActionResponse, tags=["games"])
async def apply_game_action(game_id: str, req: ApplyActionRequest) -> ApplyActionResponse:
  state = _get_game(game_id)
  ok, msg = validate_action(state, req.action)
  if not ok:
    raise HTTPException(status_code=400, detail=msg)
  new_state, events = apply_action(state, req.action, req.session_id)
  _games[game_id] = new_state
  _event_log[game_id].extend(events)
  return ApplyActionResponse(
    success=True,
    events=events,
    public_state=to_public_table_state(new_state).model_dump(),
    winner_id=new_state.winner_id,
  )


@app.get("/games/{game_id}/state", tags=["games"])
async def get_state(game_id: str) -> dict:
  state = _get_game(game_id)
  return {
    "public": to_public_table_state(state).model_dump(),
    "hands_sizes": {pid: len(h) for pid, h in state.hands.items()},
    "winner_id": state.winner_id,
  }


@app.get("/games/{game_id}/events", tags=["games"])
async def get_events(game_id: str) -> list[DomainEvent]:
  _get_game(game_id)
  return _event_log.get(game_id, [])


@app.post("/games/{game_id}/validate", tags=["games"])
async def validate(game_id: str, action: LegalAction) -> dict:
  state = _get_game(game_id)
  ok, msg = validate_action(state, action)
  return {"valid": ok, "message": msg}


@app.get("/games/{game_id}/replay", response_model=ReplayEnvelope, tags=["games"])
async def export_replay(game_id: str, session_id: str = "local") -> ReplayEnvelope:
  state = _get_game(game_id)
  return ReplayEnvelope(
    replay_id=str(uuid4()),
    game_id=game_id,
    session_id=session_id,
    events=_event_log.get(game_id, []),
    metadata={"player_names": [p.display_name for p in state.players]},
  )


def _get_game(game_id: str) -> GameState:
  if game_id not in _games:
    raise HTTPException(status_code=404, detail="game not found")
  return _games[game_id]


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_core.api:app", host="127.0.0.1", port=SERVICE_PORTS["uno-core"], reload=False)
