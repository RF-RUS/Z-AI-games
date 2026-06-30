"""Internal canonical game state — not exposed as observation truth."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from uno_schemas.game import Card, CardColor, CardValue, PlayerRef


@dataclass
class GameState:
  game_id: str
  players: list[PlayerRef]
  hands: dict[str, list[Card]]
  draw_pile: list[Card]
  discard_pile: list[Card]
  current_player_idx: int = 0
  direction: int = 1
  active_color: CardColor | None = None
  pending_draw: int = 0
  said_uno: set[str] = field(default_factory=set)
  winner_id: str | None = None
  sequence: int = 0

  @property
  def top_card(self) -> Card:
    return self.discard_pile[-1]

  @property
  def effective_color(self) -> CardColor:
    if self.active_color:
      return self.active_color
    top = self.top_card
    return top.color if top.color != CardColor.WILD else CardColor.RED

  @property
  def current_player(self) -> PlayerRef:
    return self.players[self.current_player_idx]

  def hand_size(self, player_id: str) -> int:
    return len(self.hands[player_id])

  def advance_turn(self, steps: int = 1) -> None:
    n = len(self.players)
    self.current_player_idx = (self.current_player_idx + steps * self.direction) % n

  def next_player_id(self, offset: int = 1) -> str:
    n = len(self.players)
    idx = (self.current_player_idx + offset * self.direction) % n
    return self.players[idx].player_id


def create_initial_state(
  game_id: str,
  player_names: list[str],
  seed: int | None = None,
) -> GameState:
  from uno_core.deck import build_standard_deck, shuffle_deck

  players = [
    PlayerRef(player_id=str(uuid4()), display_name=name, seat=i)
    for i, name in enumerate(player_names)
  ]
  deck = shuffle_deck(build_standard_deck(), seed)
  hands = {p.player_id: [deck.pop() for _ in range(7)] for p in players}

  # Ensure first discard is not wild draw four
  while deck[-1].value == CardValue.WILD_DRAW_FOUR:
    deck.insert(0, deck.pop())

  discard = [deck.pop()]
  active_color = discard[0].color if discard[0].color != CardColor.WILD else CardColor.RED

  return GameState(
    game_id=game_id,
    players=players,
    hands=hands,
    draw_pile=deck,
    discard_pile=discard,
    active_color=active_color if discard[0].color == CardColor.WILD else None,
  )
