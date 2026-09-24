"""Text-to-speech backends.

``PrintSpeaker`` is the zero-dependency default (also used by tests and the
scripted demo). ``Pyttsx3Speaker`` synthesizes speech fully offline via
pyttsx3 (espeak-ng on Linux) when the extra is installed.
"""

from __future__ import annotations


class PrintSpeaker:
    """Fallback speaker: prints agent replies to stdout."""

    def __init__(self, prefix: str = "AGENT") -> None:
        self.prefix = prefix
        self.spoken: list[str] = []

    def say(self, text: str) -> None:
        self.spoken.append(text)
        print(f"{self.prefix}: {text}")


class Pyttsx3Speaker:
    """Offline speech synthesis via pyttsx3 (optional dependency)."""

    def __init__(self, rate: int = 175) -> None:
        try:
            import pyttsx3
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "pyttsx3 is not installed. pip install pyttsx3 "
                "(Linux also needs espeak-ng), or run with --no-tts."
            ) from exc
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        self._echo = PrintSpeaker()

    def say(self, text: str) -> None:
        self._echo.say(text)
        self._engine.say(text)
        self._engine.runAndWait()
