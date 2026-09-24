#!/usr/bin/env python3
"""Live voice agent entrypoint.

Modes:
  --text   Type caller utterances at a prompt. Zero API keys needed; the
           full intake brain runs offline. Great for dry runs.
  (default) Microphone mode: streams audio to AssemblyAI Universal-Streaming,
           feeds finished turns to the intake brain, speaks replies with
           pyttsx3 (or prints them with --no-tts).

Requires ASSEMBLYAI_API_KEY in the environment for microphone mode only.
Set LLM_API_KEY (plus optional LLM_BASE_URL / LLM_MODEL) to upgrade field
extraction with any OpenAI-compatible model; without it, the built-in
offline parser handles extraction.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from frontdesk.dialogue import IntakeAgent
from frontdesk.intake import Business
from frontdesk.llm import LLMExtractor
from frontdesk.sink import CsvSink, MultiSink, WebhookSink
from frontdesk.tts import PrintSpeaker


def build_agent(business_path: str, today=None) -> IntakeAgent:
    business = Business.from_json(business_path)
    extractor = LLMExtractor(
        business_name=business.name,
        service_names=[s.name for s in business.services],
        today=today,
    )
    agent = IntakeAgent(
        business,
        extractor=extractor if extractor.enabled else None,
        today=today,
    )
    return agent


def build_sinks(csv_path: str, webhook_url: str | None) -> MultiSink:
    sinks = [CsvSink(csv_path)]
    if webhook_url:
        sinks.append(WebhookSink(webhook_url))
    return MultiSink(*sinks)


def persist(agent: IntakeAgent, sinks: MultiSink, speaker) -> None:
    if not agent.lead.is_complete():
        speaker.say("The call ended before I captured everything, so nothing was saved.")
        return
    sinks.save(agent.lead)
    if sinks.errors:
        speaker.say("I saved the booking locally, but one destination failed.")
    else:
        speaker.say("Your booking details are saved. Goodbye!")


def run_text_mode(agent: IntakeAgent, sinks: MultiSink, speaker) -> None:
    speaker.say(agent.greeting())
    while not agent.done:
        try:
            utterance = input("CALLER: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        speaker.say(agent.handle(utterance))
    if agent.done:
        persist(agent, sinks, speaker)


def run_mic_mode(agent: IntakeAgent, sinks: MultiSink, speaker) -> None:
    from frontdesk.stt import StreamingSTT

    api_key = os.getenv("ASSEMBLYAI_API_KEY", "")
    if not api_key:
        sys.exit(
            "ASSEMBLYAI_API_KEY is not set. Get a key at "
            "https://www.assemblyai.com/dashboard and export it, or use "
            "--text mode to run without any keys."
        )

    def on_turn_end(text: str) -> None:
        print(f"CALLER: {text}")
        reply = agent.handle(text)
        speaker.say(reply)
        if agent.done:
            persist(agent, sinks, speaker)
            raise KeyboardInterrupt  # unwind stream loop after saving

    stt = StreamingSTT(api_key=api_key, on_turn_end=on_turn_end)
    speaker.say(agent.greeting())
    try:
        stt.run()
    except KeyboardInterrupt:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Frontdesk voice intake agent")
    parser.add_argument("--business", default=str(Path(__file__).parent / "business.json"))
    parser.add_argument("--csv", default="leads.csv", help="CSV output path")
    parser.add_argument(
        "--webhook",
        default=os.getenv("INTAKE_WEBHOOK_URL"),
        help="Optional webhook URL (e.g. Google Apps Script) for captured leads",
    )
    parser.add_argument("--text", action="store_true", help="type utterances instead of using the mic")
    parser.add_argument("--no-tts", action="store_true", help="print replies instead of synthesizing speech")
    args = parser.parse_args()

    agent = build_agent(args.business)
    sinks = build_sinks(args.csv, args.webhook)

    if args.text or args.no_tts:
        speaker = PrintSpeaker()
    else:
        from frontdesk.tts import Pyttsx3Speaker

        speaker = Pyttsx3Speaker()

    if args.text:
        run_text_mode(agent, sinks, speaker)
    else:
        run_mic_mode(agent, sinks, speaker)


if __name__ == "__main__":
    main()
