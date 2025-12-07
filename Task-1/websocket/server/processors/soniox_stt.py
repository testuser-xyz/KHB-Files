#
# Soniox STT Service for Pipecat
#
import os
import json
import asyncio
from typing import AsyncGenerator
from loguru import logger
from dotenv import load_dotenv
import websockets

from pipecat.frames.frames import (
    Frame,
    AudioRawFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    StartFrame,
    EndFrame,
    CancelFrame,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.services.ai_service import AIService

load_dotenv()

class SonioxSTTService(AIService):
    """Soniox Speech-to-Text service using WebSocket API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "stt-rt-preview",
        sample_rate: int = 16000,
        audio_format: str = "pcm16",
        language_hints: list[str] | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._api_key = api_key or os.getenv("SONIOX_API_KEY")
        if not self._api_key:
            raise ValueError("Soniox API key is required")
        
        self._model = model
        self._sample_rate = sample_rate
        self._audio_format = audio_format
        self._language_hints = language_hints or ["en"]
        
        self._websocket = None
        self._receive_task = None
        self._audio_queue = asyncio.Queue()
        self._is_speaking = False

    async def start(self, frame: StartFrame):
        """Start the Soniox STT service."""
        await super().start(frame)
        try:
            # Connect to Soniox WebSocket
            url = "wss://stt-rt.soniox.com/transcribe-websocket"
            logger.info(f"🎤 [SONIOX STT] Connecting to {url}...")
            self._websocket = await websockets.connect(url)
            logger.success(f"✅ [SONIOX STT] Connected successfully!")
            
            # Send configuration
            config = {
                "api_key": self._api_key,
                "model": self._model,
                "audio_format": self._audio_format,
                "sample_rate": self._sample_rate,
                "language_hints": self._language_hints,
            }
            logger.info(f"🎤 [SONIOX STT] Sending config: model={self._model}, rate={self._sample_rate}Hz")
            await self._websocket.send(json.dumps(config))
            
            # Start receive task
            self._receive_task = asyncio.create_task(self._receive_loop())
            logger.success(f"✅ [SONIOX STT] Service started and ready to transcribe!")
        except Exception as e:
            logger.error(f"❌ [SONIOX STT] Error starting: {e}")
            await self.push_error(f"Failed to start Soniox STT: {e}")

    async def stop(self, frame: EndFrame):
        """Stop the Soniox STT service."""
        await super().stop(frame)
        try:
            if self._receive_task:
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass
            
            if self._websocket:
                # Send empty frame to gracefully close
                await self._websocket.send(b"")
                await self._websocket.close()
                self._websocket = None
            
            logger.info(f"{self} stopped")
        except Exception as e:
            logger.error(f"{self} Error stopping Soniox STT: {e}")

    async def cancel(self, frame: CancelFrame):
        """Cancel the Soniox STT service."""
        await self.stop(EndFrame())

    async def _receive_loop(self):
        """Receive transcription results from Soniox."""
        try:
            while self._websocket:
                message = await self._websocket.recv()
                data = json.loads(message)
                
                # Check for errors
                if "error_code" in data:
                    logger.error(f"Soniox STT error: {data.get('error_message')}")
                    await self.push_error(f"Soniox error: {data.get('error_message')}")
                    continue
                
                # Check for finished signal
                if data.get("finished"):
                    logger.debug("Soniox stream finished")
                    continue
                
                # Process tokens
                tokens = data.get("tokens", [])
                if tokens:
                    # Get final tokens only
                    final_tokens = [t for t in tokens if t.get("is_final")]
                    if final_tokens:
                        text = " ".join(t.get("text", "") for t in final_tokens)
                        if text.strip():
                            logger.success(f"🎤 [SONIOX STT] ✨ Transcribed: '{text}'")
                            await self.push_frame(TranscriptionFrame(text=text, user_id="", timestamp=""))
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"{self} Error in receive loop: {e}")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames."""
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStartedSpeakingFrame):
            self._is_speaking = True
            logger.info(f"🎤 [SONIOX STT] 🗣️  User started speaking - listening...")
            await self.push_frame(frame, direction)
            
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._is_speaking = False
            logger.info(f"🎤 [SONIOX STT] 🤐 User stopped speaking - processing...")
            await self.push_frame(frame, direction)
            
        elif isinstance(frame, AudioRawFrame):
            # Send audio to Soniox if connected and user is speaking
            if self._websocket and self._is_speaking:
                try:
                    # Send audio as binary
                    await self._websocket.send(frame.audio)
                    # Log every 50th audio frame to avoid spam
                    if not hasattr(self, '_audio_frame_count'):
                        self._audio_frame_count = 0
                    self._audio_frame_count += 1
                    if self._audio_frame_count % 50 == 0:
                        logger.debug(f"🎤 [SONIOX STT] Streaming audio... ({self._audio_frame_count} frames sent)")
                except Exception as e:
                    logger.error(f"❌ [SONIOX STT] Error sending audio: {e}")
            
            # Always push audio downstream
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

