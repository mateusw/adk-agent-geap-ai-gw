#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Not an official Google product. Demonstration code only: it may
# contain bugs and is not intended for production use.

"""Run the catalog agent locally — the ungoverned baseline.

A locally-run agent is NOT routed through Agent Gateway; only Agent Runtime
and Gemini Enterprise are. That is exactly what makes this useful: it proves
the agent and all three retrieval paths work on their own, so anything that
breaks after deployment is a gateway or allowlist problem, not an agent
problem.

Usage:
    python run_agent.py                      # interactive
    python run_agent.py "a rug for a patio"  # single turn
    python run_agent.py --all "a reading chair"   # same query down all three
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from catalog_agent import APP_NAME, create_app  # noqa: E402

_USER_ID = "local-operator"

# The phrasings prompts.py keys off to pin the transport. gRPC last, so an
# enforcing gateway denies the run's final call and leaves it on screen.
_PATHS = ("MCP", "REST", "SDK")


async def _turn(runner: InMemoryRunner, session_id: str, text: str) -> None:
    """Send one turn and print the model's text plus every tool call made."""
    message = types.Content(role="user", parts=[types.Part(text=text)])
    async for event in runner.run_async(
        user_id=_USER_ID, session_id=session_id, new_message=message
    ):
        for call in event.get_function_calls() or []:
            print(f"  [tool call] {call.name}")
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text, end="")
    print()


async def main() -> None:
    args = sys.argv[1:]
    run_all = "--all" in args
    if run_all:
        args.remove("--all")

    runner = InMemoryRunner(app=create_app(), app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=_USER_ID
    )

    if args:
        query = " ".join(args)
        if run_all:
            # Force each path in turn so the three are directly comparable.
            for path in _PATHS:
                await _turn(runner, session.id, f"{query} via {path}")
        else:
            await _turn(runner, session.id, query)
        return

    print("Catalog agent. Add 'via MCP', 'via REST' or 'via SDK' to pin one.")
    print("Ctrl-C or an empty line to quit.\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            return
        await _turn(runner, session.id, text)


if __name__ == "__main__":
    asyncio.run(main())
