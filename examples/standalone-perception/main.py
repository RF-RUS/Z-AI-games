"""Standalone perception merger example."""

from uno_perception.merger import build_observation
from uno_schemas.perception import DomEvidence


def main():
  dom = DomEvidence(
    snapshot={
      "top_card": {"color": "blue", "value": "skip"},
      "current_player_id": "bot",
      "draw_pile_count": 50,
    },
    confidence=0.9,
  )
  obs = build_observation("standalone-session", dom=dom)
  print(f"Observation {obs.observation_id}: confidence={obs.confidence.overall}")
  print(f"Table top: {obs.table_state.top_card if obs.table_state else None}")


if __name__ == "__main__":
  main()
