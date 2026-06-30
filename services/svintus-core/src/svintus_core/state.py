"""Svintus game state — card game with Russian rules.

Svintus (Свинтус) is a shedding-type card game similar to UNO.
Key differences from UNO:
- Players call "Svintus!" when they have one card left (instead of "UNO!")
- Penalty for forgetting to call is 3 cards (instead of 2)
- Some rule variations on stacking and challenges

For this proof-of-concept, we use the same card set as UNO
to demonstrate GamePlugin protocol works with different games.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SvintusCard:
    color: str  # red, blue, green, yellow, wild
    value: str  # 0-9, skip, reverse, draw_two, wild, wild_draw_four

    def matches(self, other: SvintusCard) -> bool:
        if self.color == "wild" or other.color == "wild":
            return True
        return self.color == other.color or self.value == other.value


@dataclass
class SvintusPlayer:
    player_id: str
    display_name: str
    seat: int


@dataclass
class SvintusState:
    game_id: str
    players: list[SvintusPlayer]
    hands: dict[str, list[SvintusCard]]
    draw_pile: list[SvintusCard]
    discard_pile: list[SvintusCard]
    current_player_idx: int = 0
    direction: int = 1
    active_color: str | None = None
    pending_draw: int = 0
    said_svintus: set[str] = field(default_factory=set)
    winner_id: str | None = None
    sequence: int = 0

    @property
    def top_card(self) -> SvintusCard:
        return self.discard_pile[-1]

    @property
    def effective_color(self) -> str:
        if self.active_color:
            return self.active_color
        top = self.top_card
        return top.color if top.color != "wild" else "red"

    @property
    def current_player(self) -> SvintusPlayer:
        return self.players[self.current_player_idx]

    def hand_size(self, player_id: str) -> int:
        return len(self.hands.get(player_id, []))

    def advance_turn(self, steps: int = 1) -> None:
        n = len(self.players)
        self.current_player_idx = (self.current_player_idx + steps * self.direction) % n

    def next_player_id(self, offset: int = 1) -> str:
        n = len(self.players)
        idx = (self.current_player_idx + offset * self.direction) % n
        return self.players[idx].player_id


def build_svintus_deck() -> list[SvintusCard]:
    """Build a standard Svintus deck (same as UNO for this PoC)."""
    colors = ["red", "blue", "green", "yellow"]
    values = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
              "skip", "reverse", "draw_two"]
    deck = []
    for color in colors:
        deck.append(SvintusCard(color=color, value="0"))
        for value in values[1:]:
            deck.append(SvintusCard(color=color, value=value))
            deck.append(SvintusCard(color=color, value=value))
    for _ in range(4):
        deck.append(SvintusCard(color="wild", value="wild"))
        deck.append(SvintusCard(color="wild", value="wild_draw_four"))
    return deck


def shuffle_deck(deck: list[SvintusCard], seed: int | None = None) -> list[SvintusCard]:
    import random
    rng = random.Random(seed)
    shuffled = list(deck)
    rng.shuffle(shuffled)
    return shuffled


def create_svintus_state(
    game_id: str,
    player_names: list[str],
    seed: int | None = None,
) -> SvintusState:
    from uuid import uuid4 as uid

    players = [
        SvintusPlayer(player_id=str(uid()), display_name=name, seat=i)
        for i, name in enumerate(player_names)
    ]
    deck = shuffle_deck(build_svintus_deck(), seed)
    hands = {p.player_id: [deck.pop() for _ in range(7)] for p in players}

    while deck[-1].value == "wild_draw_four":
        deck.insert(0, deck.pop())

    discard = [deck.pop()]
    active_color = discard[0].color if discard[0].color != "wild" else "red"

    return SvintusState(
        game_id=game_id,
        players=players,
        hands=hands,
        draw_pile=deck,
        discard_pile=discard,
        active_color=active_color if discard[0].color == "wild" else None,
    )
