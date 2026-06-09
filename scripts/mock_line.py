#!/usr/bin/env python3
"""Local mock LINE CLI for testing AI Router routing."""

import argparse
import asyncio

from app.router.ai_router import AIRouter


def mock_line_payload(text: str) -> str:
    """Run the AI Router against a text input and return the mock LINE reply."""
    router = AIRouter()
    result = asyncio.run(router.route(message=text))
    worker_response = result.get("worker_response", "我還不確定你的需求，可以再說清楚一點嗎？")
    return f"小雷收到：{worker_response}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mock LINE CLI for local AI Router testing."
    )
    parser.add_argument("text", help="Text message to send to AI Router.")
    args = parser.parse_args()

    reply = mock_line_payload(args.text)
    print(reply)


if __name__ == "__main__":
    main()
