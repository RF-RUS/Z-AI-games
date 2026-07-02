"""Deterministic tkinter test target for adapter-windows real-mode tests.

Draw button increments a visible counter and decrements the draw pile,
producing a measurable screenshot change on every click.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class MockUnoApp:
  def __init__(self) -> None:
    self.draw_count = 0
    self.pile_remaining = 80

    self.root = tk.Tk()
    self.root.title("UNO Mock Test Target")
    self.root.geometry("640x480")

    ttk.Label(self.root, text="Current: bot", name="current_player").pack(pady=4)
    ttk.Label(self.root, text="Discard: Red 5", name="discard_card").pack(pady=4)
    self.pile_label = ttk.Label(self.root, text=f"Draw pile: {self.pile_remaining}", name="draw_pile")
    self.pile_label.pack()

    hand = ttk.LabelFrame(self.root, text="Hand")
    hand.pack(fill="x", padx=8, pady=8)
    self.hand_label = ttk.Label(hand, text="Red 5 | Blue 3 | Yellow Skip", name="hand_cards")
    self.hand_label.pack()

    self.drawn_label = ttk.Label(self.root, text="Drawn: 0", name="drawn_count")
    self.drawn_label.pack(pady=2)

    actions = ttk.Frame(self.root)
    actions.pack(pady=8)
    ttk.Button(actions, text="Draw", command=self._on_draw).pack(side="left", padx=4)
    ttk.Button(actions, text="Play Red 5").pack(side="left", padx=4)

    chat = ttk.LabelFrame(self.root, text="Chat")
    chat.pack(fill="both", expand=True, padx=8, pady=8)
    ttk.Label(chat, text="Player2: hey bot, what are the rules?").pack(anchor="w")
    entry = ttk.Entry(chat)
    entry.pack(fill="x", pady=4)
    entry.insert(0, "Type message...")

  def _on_draw(self) -> None:
    self.draw_count += 1
    self.pile_remaining = max(0, self.pile_remaining - 1)
    self.drawn_label.config(text=f"Drawn: {self.draw_count}")
    self.pile_label.config(text=f"Draw pile: {self.pile_remaining}")

  def run(self) -> None:
    self.root.mainloop()


def main() -> None:
  MockUnoApp().run()


if __name__ == "__main__":
  main()
