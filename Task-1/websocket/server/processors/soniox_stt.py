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
    LLMRunFrame,
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
        audio_format: str = "s16le",  # s16le = signed 16-bit little-endian (PCM16)
        channels: int = 1,  # 1 = mono, 2 = stereo (mono is standard for voice)
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
        self._channels = channels
        self._language_hints = language_hints or ["en"]
        
        self._websocket = None
        self._receive_task = None
        self._audio_queue = asyncio.Queue()
        self._is_speaking = False
        self._pending_transcription = None  # Store final transcription until user stops speaking
        self._last_partial_transcription = None  # Store last partial transcription as fallback
        self._transcript_buffer = ""  # Accumulates text for the current utterance

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
            # Soniox requires audio_format and num_channels to be specified for PCM formats
            config = {
                "api_key": self._api_key,
                "model": self._model,
                "audio_format": self._audio_format,
                "sample_rate": self._sample_rate,
                "num_channels": self._channels,  # Soniox uses "num_channels" not "channels"
                "language_hints": self._language_hints,
            }
            logger.info(f"🎤 [SONIOX STT] Sending config: model={self._model}, rate={self._sample_rate}Hz, format={self._audio_format}, channels={self._channels}")
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
<<<<<<< HEAD
                try:
                    message = await self._websocket.recv()
                    data = json.loads(message)
                    
                    # Check for errors
                    if "error_code" in data:
                        logger.error(f"🎤 [SONIOX STT] Error: {data.get('error_message')}")
                        await self.push_error(f"Soniox error: {data.get('error_message')}")
                        continue
                    
                    # Check for finished signal
                    if data.get("finished"):
                        logger.debug("🎤 [SONIOX STT] Stream finished")
                        continue
                    
                    # Process tokens
                    tokens = data.get("tokens", [])
                    if tokens:
                        logger.debug(f"🎤 [SONIOX STT] Received {len(tokens)} tokens")
                        # Get final tokens first
                        final_tokens = [t for t in tokens if t.get("is_final")]
                        if final_tokens:
                            # Extract all text from final tokens and normalize
                            token_texts = [t.get("text", "") for t in final_tokens if t.get("text")]
                            if token_texts:
                                # Soniox tokens are cumulative; keep only the latest full string
                                text = "".join(token_texts)
                                text = " ".join(text.split())
                                if text.strip():
                                    logger.success(f"🎤 [SONIOX STT] ✨ Final transcription: '{text}'")
                                    # Replace buffer with the latest full text for this utterance
                                    self._transcript_buffer = text
                                    self._pending_transcription = self._transcript_buffer.strip()
                        else:
                            # Store partial tokens as fallback (cumulative)
                            token_texts = [t.get("text", "") for t in tokens if t.get("text")]
                            if token_texts:
                                partial_text = "".join(token_texts)
                                partial_text = " ".join(partial_text.split())
                                # Replace buffer with latest partial to avoid duplication
                                self._transcript_buffer = partial_text
                                self._last_partial_transcription = self._transcript_buffer.strip()
                                logger.debug(f"🎤 [SONIOX STT] Partial transcription: '{partial_text}'")
                except websockets.exceptions.ConnectionClosed:
                    logger.info("🎤 [SONIOX STT] WebSocket connection closed by server")
                    break
                except json.JSONDecodeError as e:
                    logger.warning(f"🎤 [SONIOX STT] Failed to parse JSON: {e}")
=======
                message = await self._websocket.recv()
                data = json.loads(message)
                
                # Check for errors
                if "error_code" in data:
                    logger.error(f"Soniox STT error: {data.get('error_message')}")
                    await self.push_error(f"Soniox error: {data.get('error_message')}")
>>>>>>> parent of 0294cac (Fixes)
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
            # Reset transcript state for a fresh utterance
            self._pending_transcription = None
            self._last_partial_transcription = None
            self._transcript_buffer = ""
            logger.info(f"🎤 [SONIOX STT] 🗣️  User started speaking - listening...")
            await self.push_frame(frame, direction)
            
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._is_speaking = False
            logger.info(f"🎤 [SONIOX STT] 🤐 User stopped speaking - processing...")
<<<<<<< HEAD
            # Send empty frame to signal end of audio stream to Soniox
            if self._websocket:
                try:
                    await self._websocket.send(b"")
                    logger.debug("🎤 [SONIOX STT] Sent end-of-stream signal to Soniox")
                except Exception as e:
                    logger.debug(f"🎤 [SONIOX STT] Could not send end-of-stream: {e}")
            
            # Wait a short time for final tokens to arrive (Soniox may send them after end-of-stream)
            await asyncio.sleep(0.5)
            
            # Send pending transcription if available (use final, fallback to partial)
            text_to_send = None
            if self._pending_transcription:
                text_to_send = self._pending_transcription
                logger.info(f"🎤 [SONIOX STT] Using final transcription: '{text_to_send}'")
            elif self._last_partial_transcription:
                text_to_send = self._last_partial_transcription
                logger.info(f"🎤 [SONIOX STT] Using partial transcription (no final received): '{text_to_send}'")
            
            if text_to_send:
                logger.success(f"🎤 [SONIOX STT] ✨ Sending TranscriptionFrame: '{text_to_send}'")
                await self.push_frame(TranscriptionFrame(text=text_to_send, user_id="", timestamp=""), direction)
                # Trigger LLM to process the transcription
                logger.info(f"🎤 [SONIOX STT] 📤 Sending LLMRunFrame to trigger LLM")
                await self.push_frame(LLMRunFrame(), direction)
                self._pending_transcription = None
                self._last_partial_transcription = None
            else:
                logger.warning("🎤 [SONIOX STT] ⚠️ No transcription available to send")
            
=======
>>>>>>> parent of 0294cac (Fixes)
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

