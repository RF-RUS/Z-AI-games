"""Deterministic tkinter test target for adapter-windows real-mode tests."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def main() -> None:
  root = tk.Tk()
  root.title("UNO Mock Test Target")
  root.geometry("640x480")

  ttk.Label(root, text="Current: bot", name="current_player").pack(pady=4)
  ttk.Label(root, text="Discard: Red 5", name="discard_card").pack(pady=4)
  ttk.Label(root, text="Draw pile: 80").pack()

  hand = ttk.LabelFrame(root, text="Hand")
  hand.pack(fill="x", padx=8, pady=8)
  ttk.Label(hand, text="Red 5 | Blue 3 | Yellow Skip").pack()

  actions = ttk.Frame(root)
  actions.pack(pady=8)
  ttk.Button(actions, text="Draw").pack(side="left", padx=4)
  ttk.Button(actions, text="Play Red 5").pack(side="left", padx=4)

  chat = ttk.LabelFrame(root, text="Chat")
  chat.pack(fill="both", expand=True, padx=8, pady=8)
  ttk.Label(chat, text="Player2: hey bot, what are the rules?").pack(anchor="w")
  entry = ttk.Entry(chat)
  entry.pack(fill="x", pady=4)
  entry.insert(0, "Type message...")

  root.mainloop()


if __name__ == "__main__":
  main()
