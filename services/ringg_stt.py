"""Ringg Parrot STT as a Pipecat STTService, wrapping ringglabs AsyncClient.stream."""

from typing import AsyncGenerator

from loguru import logger

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
)
from pipecat.services.stt_service import STTService
from pipecat.utils.time import time_now_iso8601

from ringglabs.stt import AsyncClient
from ringglabs.stt.errors import TimeoutError as RinggTimeoutError
from ringglabs.stt.models import TranscriptEvent


class RinggSTTService(STTService):
    """Streams 16kHz int16 audio to Ringg Parrot STT over websocket.

    Audio chunks go out via run_stt(); a background task reads transcript
    events and pushes Interim/TranscriptionFrames.
    """

    def __init__(self, *, api_key: str, language: str = "en",
                 sample_rate: int = 16000, **kwargs):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._api_key = api_key
        self._language = language
        self._client: AsyncClient | None = None
        self._session = None
        self._receive_task = None

    async def start(self, frame: StartFrame):
        await super().start(frame)
        await self._connect()

    async def stop(self, frame: EndFrame):
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame):
        await super().cancel(frame)
        await self._disconnect()

    async def _connect(self):
        self._client = AsyncClient(api_key=self._api_key)
        self._session = self._client.stream(
            sample_rate=self.sample_rate or 16000,
            encoding="int16",
            language=self._language,
            mode="stream",
        )
        ready = await self._session.open()
        logger.info(f"Ringg STT connected: request_id={ready.request_id}")
        self._receive_task = self.create_task(self._receive_loop(), "ringg_stt_receive")

    async def _disconnect(self):
        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None
        if self._session:
            try:
                await self._session.end()
            except Exception:
                pass
            await self._session.close()
            self._session = None
        if self._client:
            await self._client.close()
            self._client = None

    async def _receive_loop(self):
        while self._session:
            try:
                event = await self._session.recv_event()
            except RinggTimeoutError:
                # 30s of silence — keep the connection alive and keep listening
                try:
                    await self._session.ping()
                except Exception:
                    break
                continue
            except Exception as e:
                logger.warning(f"Ringg STT receive loop ended: {e}")
                break
            if isinstance(event, TranscriptEvent) and event.transcription:
                if event.is_final:
                    await self.push_frame(TranscriptionFrame(
                        text=event.transcription, user_id="",
                        timestamp=time_now_iso8601(), result=event.raw))
                else:
                    await self.push_frame(InterimTranscriptionFrame(
                        text=event.transcription, user_id="",
                        timestamp=time_now_iso8601(), result=event.raw))

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        if self._session:
            await self._session.send_audio(audio)
        yield None
