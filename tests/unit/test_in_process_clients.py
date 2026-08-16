"""Contract tests for InProcessAdapterClient.

The in-process client must accept the SAME keyword contract as the HTTP
GenericAdapterClient it delegates to — flow_controller.py calls both through
one interface, so a signature drift here breaks every in-process session
(mock runs, tests, run-windows-agent.py --in-process) with a TypeError.
"""

from uno_orchestrator.in_process_clients import InProcessAdapterClient


def _client() -> InProcessAdapterClient:
    # map_action() delegates synchronously to GenericAdapterClient and never
    # touches the ASGI app, so a dummy app is fine here.
    return InProcessAdapterClient("mock", app=object())


def test_map_action_accepts_hand_cards_kwarg():
  client = _client()
  req = client.map_action(
    "play_card",
    profile_id="local-mock-uno",
    card_color="red",
    card_value="5",
    hand_cards=[{"color": "red", "number": "5", "slot_index": 0}],
  )
  # Mapping itself is the delegate's job (mock maps play_card → click);
  # this test pins the KWARG CONTRACT only.
  assert req.domain_action == "play_card"


def test_map_action_accepts_payload_kwarg():
  client = _client()
  req = client.map_action("draw_card", profile_id="local-mock-uno", payload={"draw_target": [100, 200]})
  assert req is not None
