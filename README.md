# Frontdesk Voice Agent

A voice intake agent that answers calls for a small service business, captures
booking/quote details through a natural phone conversation, and logs every lead
to CSV or straight into a Google Sheet.

Built on **AssemblyAI Universal-Streaming** (v3) for real-time speech-to-text,
with a deterministic intake brain that works fully offline and an optional LLM
layer for messier utterances.

**Vertical:** mobile auto detailing (configurable to any service business via
one JSON file). The demo business, *Toledo Shine Mobile Detailing*, takes
inbound calls, collects name → phone → service → date → time, confirms the
details back, handles corrections ("actually, make it 3 pm"), and saves the
booking.

## Why this is useful

Small service businesses miss calls while doing the work. Every missed call is
a lost $80–$180 job. Frontdesk Voice Agent answers every call, captures the
lead in a structured format, and hands the owner a spreadsheet of confirmed
bookings to call back — no receptionist, no voicemail black hole.

## Architecture

```
 caller voice
     │
     ▼
┌─────────────────────────────┐
│ AssemblyAI Universal-       │  wss://streaming.assemblyai.com (v3 SDK)
│ Streaming STT               │  turn-based transcripts, end-of-turn detection
└─────────────┬───────────────┘
              │ finished turn text
              ▼
┌─────────────────────────────┐
│ Intake brain                │  slot-filling state machine:
│  · offline parser (default) │  name → phone → service → date/time → confirm
│  · optional LLM extractor   │  spoken-number/date/time parsing, corrections,
│    (any OpenAI-compatible   │  LLM fills gaps, deterministic parser wins ties
│     endpoint)               │
└─────────────┬───────────────┘
              │ agent reply
              ▼
┌─────────────────────────────┐
│ TTS                         │  pyttsx3 offline synthesis (or print)
└─────────────────────────────┘
              │ completed lead
              ▼
┌─────────────────────────────┐
│ Sinks                       │  CSV file + optional webhook → Google Sheet
└─────────────────────────────┘
```

## Quickstart

### 1. Zero-key demo (works right now)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python demo.py
```

A scripted caller books an appointment — including a mid-call correction — and
the captured lead lands in `demo-output/leads.csv`. Record this for a demo
video; it exercises the exact code path the live agent uses.

### 2. Text mode (type as the caller, still zero keys)

```bash
python main.py --text
```

### 3. Live microphone mode

```bash
cp .env.example .env        # paste your AssemblyAI key
export ASSEMBLYAI_API_KEY=…
pip install pyaudio pyttsx3 # mic capture + offline TTS
python main.py
```

Speak; the agent replies out loud and saves the lead to `leads.csv`.
Use `--no-tts` to print replies instead of synthesizing speech.

### 4. Live API mode without a microphone

```bash
python live_demo.py call.pcm   # 16 kHz PCM16 mono file
```

Streams an audio file to the real Universal-Streaming API as if it were the
microphone — same code path as mic mode, for machines with no audio hardware
and for reproducible demo recordings. Writes the captured lead, a transcript,
and a timestamped event log to `demo-output/`.

### Optional: LLM extraction

Set `LLM_API_KEY` (plus `LLM_BASE_URL` / `LLM_MODEL`) in `.env` to upgrade
field extraction with any OpenAI-compatible chat endpoint — OpenAI, OpenRouter,
or a local Ollama (`http://localhost:11434/v1`). Without it, the built-in
parser handles extraction; if the LLM call fails for any reason, the agent
falls back to the parser mid-call and keeps going.

### Optional: leads straight into a Google Sheet

1. Create a Sheet, then **Extensions → Apps Script** and paste:

   ```javascript
   function doPost(e) {
     const d = JSON.parse(e.postData.contents);
     SpreadsheetApp.getActiveSheet().appendRow([
       d.captured_at, d.business, d.name, d.phone,
       d.service, d.date, d.time, d.address, d.notes,
     ]);
     return ContentService.createTextOutput("ok");
   }
   ```

2. **Deploy → New deployment → Web app**, execute as you, access "Anyone".
3. `export INTAKE_WEBHOOK_URL=<web app URL>` (or pass `--webhook`).

Every captured lead is POSTed as JSON and appended as a row.

## Configure for a real business

Edit `business.json` — name, agent name, services with prices/durations and
spoken aliases. The greeting, service menu, and extraction all follow the file.
No code changes needed to re-skin it for a plumber, salon, or landscaping crew.

## Testing

```bash
pip install -r requirements-dev.txt
pytest            # 69 tests, all non-network parts
```

Covers spoken phone/date/time parsing, service matching, the full dialogue
state machine (happy path, corrections, ambiguous answers, LLM failure
fallback), CSV/webhook sinks, and LLM response parsing.

## AssemblyAI API usage (verified)

- Universal-Streaming v3 SDK (`assemblyai` 1.5.5): `StreamingClient`,
  `StreamingEvents.Turn`, `StreamingParameters(sample_rate=16000,
  format_turns=True)` against `streaming.assemblyai.com`.
- Turn-based intake: the agent acts on `end_of_turn` transcripts and requests
  the formatted turn via `StreamingSessionParameters(format_turns=True)`,
  exactly as the quickstart prescribes.
- 50 ms PCM16 mono chunks per the audio requirements; voice-agent settings
  follow the docs' recommendation to consume unformatted turns for low
  latency.
- Verified 2026-09-24 against the live docs
  (<https://www.assemblyai.com/docs/speech-to-text/universal-streaming>) and
  the installed SDK. Note: the docs' `aai.extras.MicrophoneStream` helper no
  longer exists in SDK 1.5.5 — this repo streams mic chunks through
  `StreamingClient.stream(iterable_of_bytes)` instead.

## Roadmap

- Barge-in: interrupt the agent mid-reply using partial turns (`on_partial`).
- `keyterms_prompt` seeded from `business.json` service names for higher
  recognition accuracy on brand vocabulary.
- Twilio SIP trunk so the agent answers a real phone number.
- Slot-aware date/time validation against an availability calendar.

## AI assistance disclosure

This project was designed and built with AI assistance (Kimi Code CLI) for the
AssemblyAI Voice Agent Hackathon. Every AssemblyAI API detail was verified
against the live documentation and the installed SDK at build time, and the
non-network test-suite (69 tests) passes. Human direction, review, and testing
by Nick Toledo / Toledo Technologies LLC.

## License

MIT — see [LICENSE](LICENSE).
