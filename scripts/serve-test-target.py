#!/usr/bin/env python3
"""Serve local UNO mock test target for adapter-web Playwright tests."""

import argparse
import http.server
import socketserver
from pathlib import Path

TARGET_DIR = Path(__file__).resolve().parent.parent / "services" / "adapter-web" / "test-target"
DEFAULT_PORT = 8765


class Handler(http.server.SimpleHTTPRequestHandler):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, directory=str(TARGET_DIR), **kwargs)


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("--port", type=int, default=DEFAULT_PORT)
  args = parser.parse_args()
  with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
    print(f"Serving test target at http://127.0.0.1:{args.port}/")
    httpd.serve_forever()


if __name__ == "__main__":
  main()
