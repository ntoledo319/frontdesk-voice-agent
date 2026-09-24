"""AssemblyAI Universal-Streaming speech-to-text wrapper.

Built against the v3 streaming SDK and verified on 2026-09-24 two ways:

- Live docs: https://www.assemblyai.com/docs/speech-to-text/universal-streaming
  (StreamingClient / StreamingEvents / StreamingParameters quickstart,
  turn model, end-of-turn handling, format_turns follow-up).
- Installed SDK introspection: assemblyai 1.5.5 (latest on PyPI).
  ``StreamingClient.stream`` accepts ``bytes | Iterable[bytes]`` and the docs
  recommend 50 ms of PCM16 mono audio per message, so this module ships its
  own PyAudio microphone generator. (The docs' ``aai.extras.MicrophoneStream``
  helper no longer exists in SDK 1.5.5.)

The SDK is imported lazily so the rest of the package (and the test-suite)
works without it installed.
"""

from __future__ import annotations

from typing import Callable, Iterator

SAMPLE_RATE = 16000
CHUNK_MS = 50  # docs recommend 50 ms of audio per message


def microphone_chunks(
    sample_rate: int = SAMPLE_RATE, chunk_ms: int = CHUNK_MS
) -> Iterator[bytes]:
    """Yield PCM16 mono microphone chunks forever (PyAudio required)."""
    try:
        import pyaudio
    except ImportError as exc:  # pragma: no cover - depends on host audio
        raise RuntimeError(
            "Microphone streaming needs PyAudio: pip install pyaudio "
            "(system package portaudio19-dev on Debian/Ubuntu)"
        ) from exc

    audio = pyaudio.PyAudio()
    frames = sample_rate * chunk_ms // 1000
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=sample_rate,
        input=True,
        frames_per_buffer=frames,
    )
    try:  # pragma: no cover - depends on host audio
        while True:
            yield stream.read(frames, exception_on_overflow=False)
    finally:  # pragma: no cover
        stream.stop_stream()
        stream.close()
        audio.terminate()


class StreamingSTT:
    """Streams microphone audio to AssemblyAI and emits finished turns.

    Parameters
    ----------
    api_key:
        AssemblyAI API key.
    on_turn_end:
        Called with the transcript text each time the caller finishes a
        speaking turn (``end_of_turn`` is true).
    on_partial:
        Optional callback for in-progress turn text (useful for barge-in).
    audio_source:
        Any iterable of PCM16 mono byte chunks at ``sample_rate``.
        Defaults to the microphone via :func:`microphone_chunks`.
    """

    def __init__(
        self,
        api_key: str,
        on_turn_end: Callable[[str], None],
        on_partial: Callable[[str], None] | None = None,
        sample_rate: int = SAMPLE_RATE,
        audio_source: Iterator[bytes] | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("AssemblyAI API key is required")
        self.api_key = api_key
        self.sample_rate = sample_rate
        self._audio_source = audio_source
        self._on_turn_end = on_turn_end
        self._on_partial = on_partial
        self._client = None

    def _build_client(self):
        from assemblyai.streaming.v3 import (
            BeginEvent,
            StreamingClient,
            StreamingClientOptions,
            StreamingError,
            StreamingEvents,
            StreamingParameters,
            StreamingSessionParameters,
            TerminationEvent,
            TurnEvent,
        )

        def on_begin(self_client, event: BeginEvent) -> None:
            pass  # session started

        def on_turn(self_client, event: TurnEvent) -> None:
            if event.end_of_turn:
                if not event.turn_is_formatted:
                    # Ask for a formatted version of the final turn, per the
                    # quickstart (punctuation + inverse text normalization).
                    self_client.set_params(
                        StreamingSessionParameters(format_turns=True)
                    )
                text = (event.transcript or "").strip()
                if text:
                    self._on_turn_end(text)
            elif self._on_partial and event.transcript:
                self._on_partial(event.transcript)

        def on_terminated(self_client, event: TerminationEvent) -> None:
            pass

        def on_error(self_client, error: StreamingError) -> None:
            raise RuntimeError(f"AssemblyAI streaming error: {error}")

        client = StreamingClient(
            StreamingClientOptions(
                api_key=self.api_key,
                api_host="streaming.assemblyai.com",
            )
        )
        client.on(StreamingEvents.Begin, on_begin)
        client.on(StreamingEvents.Turn, on_turn)
        client.on(StreamingEvents.Termination, on_terminated)
        client.on(StreamingEvents.Error, on_error)
        self._connect_params = StreamingParameters(
            sample_rate=self.sample_rate,
            format_turns=True,
        )
        return client

    def run(self) -> None:
        """Connect, stream audio, and block until the source is exhausted."""
        client = self._build_client()
        client.connect(self._connect_params)
        source = (
            self._audio_source
            if self._audio_source is not None
            else microphone_chunks(self.sample_rate)
        )
        try:
            client.stream(source)
        finally:
            client.disconnect(terminate=True)
