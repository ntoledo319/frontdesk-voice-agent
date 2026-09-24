"""Frontdesk Voice Agent — a voice intake agent for small service businesses.

Pipeline: AssemblyAI Universal-Streaming STT -> intake brain (LLM or offline
rules) -> TTS, with captured bookings written to CSV and/or a webhook
(e.g. a Google Apps Script endpoint bound to a Google Sheet).
"""

__version__ = "0.1.0"
