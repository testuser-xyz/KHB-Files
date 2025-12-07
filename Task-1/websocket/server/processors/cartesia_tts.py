#
# Cartesia TTS Service for Pipecat
#
import os
from typing import AsyncGenerator
from loguru import logger
from dotenv import load_dotenv

try:
    from cartesia import AsyncCartesia
except ImportError:
    logger.warning("Cartesia SDK not installed. Run: pip install cartesia")
    AsyncCartesia = None

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    LLMFullResponseEndFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    StartFrame,
    EndFrame,
    CancelFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.ai_service import AIService

load_dotenv()

class CartesiaTTSService(AIService):
    """Cartesia Text-to-Speech service using WebSocket API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str = "694f9389-aac1-45b6-b726-9d9369183238",  # Default voice
        model_id: str = "sonic-3",
        sample_rate: int = 16000,
        encoding: str = "pcm_s16le",
        language: str = "en",
        **kwargs
    ):
        super().__init__(**kwargs)
        self._api_key = api_key or os.getenv("CARTESIA_API_KEY")
        if not self._api_key:
            raise ValueError("Cartesia API key is required")
        
        self._voice_id = voice_id
        self._model_id = model_id
        self._sample_rate = sample_rate
        self._encoding = encoding
        self._language = language
        
        self._client = None
        self._websocket = None
        self._text_buffer = ""

    async def start(self, frame: StartFrame):
        """Start the Cartesia TTS service."""
        await super().start(frame)
        try:
            if AsyncCartesia is None:
                raise ImportError("Cartesia SDK not installed")
            
            logger.info(f"🔊 [CARTESIA TTS] Initializing client...")
            self._client = AsyncCartesia(api_key=self._api_key)
            logger.info(f"🔊 [CARTESIA TTS] Opening WebSocket connection...")
            self._websocket = await self._client.tts.websocket()
            logger.success(f"✅ [CARTESIA TTS] Service started! Voice: {self._voice_id[:8]}..., Model: {self._model_id}")
        except Exception as e:
            logger.error(f"❌ [CARTESIA TTS] Error starting: {e}")
            await self.push_error(f"Failed to start Cartesia TTS: {e}")

    async def stop(self, frame: EndFrame):
        """Stop the Cartesia TTS service."""
        await super().stop(frame)
        try:
            if self._websocket:
                await self._websocket.close()
                self._websocket = None
            
            if self._client:
                await self._client.close()
                self._client = None
            
            logger.info(f"{self} stopped")
        except Exception as e:
            logger.error(f"{self} Error stopping Cartesia TTS: {e}")

    async def cancel(self, frame: CancelFrame):
        """Cancel the Cartesia TTS service."""
        await self.stop(EndFrame())

    async def _generate_speech(self, text: str) -> AsyncGenerator[bytes, None]:
        """Generate speech from text using Cartesia."""
        try:
            if not self._websocket:
                logger.error("❌ [CARTESIA TTS] WebSocket not connected")
                return
            
            logger.info(f"🔊 [CARTESIA TTS] 🎵 Generating speech for: '{text[:100]}...'")
            
            # Send request to Cartesia
            output_generator = await self._websocket.send(
                model_id=self._model_id,
                transcript=text,
                voice={"mode": "id", "id": self._voice_id},
                output_format={
                    "container": "raw",
                    "encoding": self._encoding,
                    "sample_rate": self._sample_rate,
                },
                language=self._language,
                stream=True,
            )
            
            # Stream audio chunks
            chunk_count = 0
            async for chunk in output_generator:
                if chunk.audio:
                    chunk_count += 1
                    yield chunk.audio
            
            logger.success(f"🔊 [CARTESIA TTS] ✅ Generated {chunk_count} audio chunks")
                    
        except Exception as e:
            logger.error(f"❌ [CARTESIA TTS] Error generating speech: {e}")
            await self.push_error(f"Cartesia TTS error: {e}")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames."""
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            # Buffer text
            self._text_buffer += frame.text
            logger.debug(f"🔊 [CARTESIA TTS] 📝 Buffering text: '{frame.text}' (total: {len(self._text_buffer)} chars)")
            # Don't push text frame downstream if we're generating audio
            
        elif isinstance(frame, LLMFullResponseEndFrame):
            # When LLM response is complete, generate speech for buffered text
            if self._text_buffer.strip():
                try:
                    logger.info(f"🔊 [CARTESIA TTS] 🎬 Starting TTS for buffered text ({len(self._text_buffer)} chars)")
                    await self.push_frame(TTSStartedFrame())
                    
                    audio_frames_sent = 0
                    async for audio_chunk in self._generate_speech(self._text_buffer):
                        await self.push_frame(
                            TTSAudioRawFrame(
                                audio=audio_chunk,
                                sample_rate=self._sample_rate,
                                num_channels=1,
                            )
                        )
                        audio_frames_sent += 1
                    
                    await self.push_frame(TTSStoppedFrame())
                    logger.success(f"🔊 [CARTESIA TTS] 🎉 Sent {audio_frames_sent} audio frames to output")
                    self._text_buffer = ""
                    
                except Exception as e:
                    logger.error(f"❌ [CARTESIA TTS] Error in TTS generation: {e}")
                    # Fallback: push text if TTS fails
                    logger.warning(f"🔊 [CARTESIA TTS] ⚠️  Falling back to text output")
                    await self.push_frame(TextFrame(text=self._text_buffer))
                    self._text_buffer = ""
            
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

