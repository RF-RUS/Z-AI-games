"""Deck construction and shuffling."""

from __future__ import annotations

import random
import secrets
from copy import deepcopy

from uno_schemas.game import Card, CardColor, CardValue


def build_standard_deck() -> list[Card]:
  deck: list[Card] = []
  colors = [CardColor.RED, CardColor.YELLOW, CardColor.GREEN, CardColor.BLUE]
  number_values = [
    CardValue.ZERO, CardValue.ONE, CardValue.TWO, CardValue.THREE, CardValue.FOUR,
    CardValue.FIVE, CardValue.SIX, CardValue.SEVEN, CardValue.EIGHT, CardValue.NINE,
  ]
  action_values = [CardValue.SKIP, CardValue.REVERSE, CardValue.DRAW_TWO]

  for color in colors:
    deck.append(Card(color=color, value=CardValue.ZERO))
    for value in number_values[1:]:
      deck.extend([Card(color=color, value=value)] * 2)
    for value in action_values:
      deck.extend([Card(color=color, value=value)] * 2)

  for _ in range(4):
    deck.append(Card(color=CardColor.WILD, value=CardValue.WILD))
    deck.append(Card(color=CardColor.WILD, value=CardValue.WILD_DRAW_FOUR))

  return deck


def shuffle_deck(deck: list[Card], seed: int | None = None) -> list[Card]:
  shuffled = deepcopy(deck)
  rng = random.Random(seed if seed is not None else secrets.randbelow(2**32))
  rng.shuffle(shuffled)
  return shuffled
