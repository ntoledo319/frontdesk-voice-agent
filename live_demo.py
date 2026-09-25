#!/usr/bin/env python3
"""Live AssemblyAI demo with file-fed audio (no microphone needed).

Streams a PCM16 mono 16 kHz audio file through the real Universal-Streaming
API as if it were the microphone, runs the production IntakeAgent on every
finished turn, and saves the captured lead — the exact code path
``main.py`` uses, with a file standing in for PyAudio.

Usage:
    python live_demo.py [audio.pcm]

Reads ASSEMBLYAI_API_KEY from the environment or from a local .env file
(see .env.example). Writes:
    demo-output/live-leads.csv      captured lead
    demo-output/live-transcript.txt human-readable call transcript
    demo-output/live-log.json       timestamped event log (partials, turns,
                                    replies) for evidence and video replay
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from frontdesk.dialogue import IntakeAgent
from frontdesk.intake import Business
from frontdesk.sink import CsvSink
from frontdesk.stt import CHUNK_MS, SAMPLE_RATE, StreamingSTT

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "demo-output"
CHUNK_BYTES = SAMPLE_RATE * 2 * CHUNK_MS // 1000


def load_env() -> None:
    """Populate os.environ from a local .env without overriding real env."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def file_chunks(pcm_path: Path):
    """Yield 50 ms PCM16 chunks in real time, like a live microphone."""
    with pcm_path.open("rb") as fh:
        t0 = time.monotonic()
        sent = 0
        while chunk := fh.read(CHUNK_BYTES):
            yield chunk
            sent += len(chunk)
            target = t0 + sent / (SAMPLE_RATE * 2)
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)


def main() -> None:
    load_env()
    api_key = os.getenv("ASSEMBLYAI_API_KEY", "")
    if not api_key:
        sys.exit("ASSEMBLYAI_API_KEY is not set (env or .env). See .env.example.")

    pcm_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if pcm_path is None or not pcm_path.exists():
        sys.exit(f"usage: python live_demo.py <audio.pcm>  (16 kHz PCM16 mono)")

    OUT_DIR.mkdir(exist_ok=True)
    business = Business.from_json(ROOT / "business.json")
    agent = IntakeAgent(business, today=date.today())
    sink = CsvSink(OUT_DIR / "live-leads.csv")

    events: list[dict] = []
    t0 = time.monotonic()

    def log(kind: str, text: str) -> None:
        events.append({"t": round(time.monotonic() - t0, 2), "kind": kind,
                       "text": text})

    def on_partial(text: str) -> None:
        log("partial", text)
        print(f"  … {text}")

    def on_turn_end(text: str) -> None:
        log("turn", text)
        print(f"CALLER: {text}")
        reply = agent.handle(text)
        log("reply", reply)
        print(f"AGENT:  {reply}")

    print("=" * 72)
    print(f"LIVE DEMO: streaming {pcm_path.name} to AssemblyAI Universal-Streaming")
    print(f"           inbound call to {business.name}")
    print("=" * 72)
    greeting = agent.greeting()
    log("reply", greeting)
    print(f"AGENT:  {greeting}")

    stt = StreamingSTT(
        api_key=api_key,
        on_turn_end=on_turn_end,
        on_partial=on_partial,
        audio_source=file_chunks(pcm_path),
    )
    stt.run()

    print("-" * 72)
    if agent.lead.is_complete():
        path = sink.save(agent.lead)
        log("saved", str(path))
        print(f"LEAD CAPTURED -> {path}")
        print(agent.lead.summary())
    else:
        log("incomplete", repr(agent.lead))
        print("Call ended with an incomplete lead:", agent.lead)

    (OUT_DIR / "live-log.json").write_text(json.dumps(events, indent=2))
    lines = []
    for e in events:
        if e["kind"] == "turn":
            lines.append(f"[{e['t']:6.2f}s] CALLER: {e['text']}")
        elif e["kind"] == "reply":
            lines.append(f"[{e['t']:6.2f}s] AGENT:  {e['text']}")
        elif e["kind"] in ("saved", "incomplete"):
            lines.append(f"[{e['t']:6.2f}s] {e['kind'].upper()}: {e['text']}")
    (OUT_DIR / "live-transcript.txt").write_text("\n".join(lines) + "\n")
    print(f"event log -> {OUT_DIR / 'live-log.json'}")
    print(f"transcript -> {OUT_DIR / 'live-transcript.txt'}")

    if not agent.lead.is_complete():
        sys.exit(1)


if __name__ == "__main__":
    main()
