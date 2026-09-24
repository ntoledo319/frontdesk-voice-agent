#!/usr/bin/env python3
"""Scripted end-to-end demo: a simulated caller books a detailing appointment.

No microphone, no API keys, no network. Runs the real IntakeAgent against a
scripted caller (including a correction at confirmation time) and writes the
captured lead to demo-output/leads.csv — the same code path the live agent
uses. Record this script's output for the hackathon demo video.
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from frontdesk.dialogue import IntakeAgent
from frontdesk.intake import Business
from frontdesk.sink import CsvSink
from frontdesk.tts import PrintSpeaker

SCRIPT = [
    "Hi, my name is Dana Whitfield.",
    "It's five five five, two one four, eight six nine oh.",
    "I'd like the full interior detail. It's an SUV with two car seats, if that matters.",
    "Does next Friday work?",
    "Around two thirty pm.",
    "Hmm, actually can we make it three pm instead?",
    "Yes, that's right.",
]

DELAY = 0.4  # seconds between turns, for watchable demo recordings


def main() -> None:
    out_dir = Path(__file__).parent / "demo-output"
    business = Business.from_json(Path(__file__).parent / "business.json")
    agent = IntakeAgent(business, today=date.today())
    speaker = PrintSpeaker()
    sink = CsvSink(out_dir / "leads.csv")

    print("=" * 72)
    print(f"DEMO: simulated inbound call to {business.name}")
    print("=" * 72)
    speaker.say(agent.greeting())
    time.sleep(DELAY)

    for line in SCRIPT:
        print(f"CALLER: {line}")
        time.sleep(DELAY)
        speaker.say(agent.handle(line))
        time.sleep(DELAY)
        if agent.done:
            break

    print("-" * 72)
    if agent.lead.is_complete():
        path = sink.save(agent.lead)
        print(f"LEAD CAPTURED -> {path}")
        print(agent.lead.summary())
    else:
        print("Demo ended with an incomplete lead (this is a bug):", agent.lead)
        sys.exit(1)


if __name__ == "__main__":
    main()
