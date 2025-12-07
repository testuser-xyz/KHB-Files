#
# Soniox STT Service for Pipecat
#
import os
import json
import asyncio
import re
from typing import AsyncGenerator, Optional, Dict, Any
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

SONIOX_WEBSOCKET_URL = "wss://stt-rt.soniox.com/transcribe-websocket"


class SonioxSTTService(AIService):
    """Soniox Speech-to-Text service using WebSocket API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "stt-rt-v3",
        sample_rate: int = 16000,
        audio_format: str = "auto",  # "auto" or "pcm_s16le" for raw PCM
        channels: int = 1,  # 1 = mono, 2 = stereo (mono is standard for voice)
        language_hints: list[str] | None = None,
        enable_language_identification: bool = True,
        enable_speaker_diarization: bool = True,
        enable_endpoint_detection: bool = True,
        context: Dict[str, Any] | None = None,
        translation: Dict[str, Any] | None = None,
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
        self._enable_language_identification = enable_language_identification
        self._enable_speaker_diarization = enable_speaker_diarization
        self._enable_endpoint_detection = enable_endpoint_detection
        self._context = context
        self._translation = translation
        
        self._websocket = None
        self._receive_task = None
        self._audio_queue = asyncio.Queue()
        self._is_speaking = False
        self._final_tokens: list[dict] = []  # Accumulate final tokens
        self._last_non_final_tokens: list[dict] = []  # Store latest non-final tokens
        self._current_speaker: Optional[str] = None
        self._current_language: Optional[str] = None

    def _get_config(self) -> dict:
        """Build Soniox STT configuration based on reference implementation."""
        config = {
            "api_key": self._api_key,
            "model": self._model,
            "language_hints": self._language_hints,
            "enable_language_identification": self._enable_language_identification,
            "enable_speaker_diarization": self._enable_speaker_diarization,
            "enable_endpoint_detection": self._enable_endpoint_detection,
        }
        
        # Add context if provided
        if self._context:
            config["context"] = self._context
        
        # Audio format configuration
        if self._audio_format == "auto":
            config["audio_format"] = "auto"
        elif self._audio_format == "pcm_s16le" or self._audio_format == "s16le":
            config["audio_format"] = "pcm_s16le"
            config["sample_rate"] = self._sample_rate
            config["num_channels"] = self._channels
        else:
            # Fallback for other formats
            config["audio_format"] = self._audio_format
            if self._sample_rate:
                config["sample_rate"] = self._sample_rate
            if self._channels:
                config["num_channels"] = self._channels
        
        # Translation configuration
        if self._translation:
            config["translation"] = self._translation
        
        return config

    async def _reconnect_websocket(self):
        """Reconnect to Soniox WebSocket if connection is lost."""
        try:
            # Close existing connection if any
            if self._websocket:
                try:
                    await self._websocket.close()
                except Exception:
                    pass
                self._websocket = None
            
            # Cancel existing receive task if any
            if self._receive_task:
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass
                self._receive_task = None
            
            # Connect to Soniox WebSocket
            logger.info(f"🎤 [SONIOX STT] Reconnecting to {SONIOX_WEBSOCKET_URL}...")
            self._websocket = await websockets.connect(SONIOX_WEBSOCKET_URL)
            logger.success(f"✅ [SONIOX STT] Reconnected successfully!")
            
            # Send configuration
            config = self._get_config()
            logger.info(f"🎤 [SONIOX STT] Sending config: model={self._model}, rate={self._sample_rate}Hz, format={self._audio_format}, channels={self._channels}")
            await self._websocket.send(json.dumps(config))
            
            # Reset token tracking
            self._final_tokens = []
            self._last_non_final_tokens = []
            self._current_speaker = None
            self._current_language = None
            
            # Start receive task
            self._receive_task = asyncio.create_task(self._receive_loop())
            logger.success(f"✅ [SONIOX STT] Ready to transcribe!")
            return True
        except Exception as e:
            logger.error(f"❌ [SONIOX STT] Error reconnecting: {e}")
            self._websocket = None
            return False

    async def start(self, frame: StartFrame):
        """Start the Soniox STT service."""
        await super().start(frame)
        await self._reconnect_websocket()

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
                try:
                    await self._websocket.close()
                except Exception:
                    pass
                self._websocket = None
            
            logger.info(f"{self} stopped")
        except Exception as e:
            logger.error(f"{self} Error stopping Soniox STT: {e}")

    async def cancel(self, frame: CancelFrame):
        """Cancel the Soniox STT service."""
        await self.stop(EndFrame())

    def _render_tokens(self, final_tokens: list[dict], non_final_tokens: list[dict]) -> str:
        """Convert tokens into a readable transcript (based on reference implementation)."""
        text_parts: list[str] = []
        current_speaker: Optional[str] = None
        current_language: Optional[str] = None

        # Process all tokens in order
        for token in final_tokens + non_final_tokens:
            text = token.get("text", "")
            if not text:
                continue
                
            speaker = token.get("speaker")
            language = token.get("language")
            is_translation = token.get("translation_status") == "translation"

            # Speaker changed -> add a speaker tag
            if speaker is not None and speaker != current_speaker:
                if current_speaker is not None:
                    text_parts.append("\n\n")
                current_speaker = speaker
                current_language = None  # Reset language on speaker changes
                text_parts.append(f"Speaker {current_speaker}:")

            # Language changed -> add a language or translation tag
            if language is not None and language != current_language:
                current_language = language
                prefix = "[Translation] " if is_translation else ""
                text_parts.append(f"\n{prefix}[{current_language}] ")
                text = text.lstrip()

            text_parts.append(text)

        return "".join(text_parts)

    def _clean_transcription(self, text: str) -> str:
        """Clean transcription text by removing speaker tags and language tags for LLM processing."""
        # Remove speaker tags (e.g., "Speaker 1:", "Speaker 2:")
        text = re.sub(r'Speaker\s+\d+:\s*', '', text)
        # Remove language tags (e.g., "[en]", "[Translation] [es]")
        text = re.sub(r'\[Translation\]\s*', '', text)
        text = re.sub(r'\[[a-z]{2}\]\s*', '', text)
        # Remove any remaining metadata like "<end>"
        text = re.sub(r'<end>', '', text)
        # Clean up whitespace
        text = " ".join(text.split())
        return text.strip()

    async def _receive_loop(self):
        """Receive transcription results from Soniox (based on reference implementation)."""
        try:
            while self._websocket:
                try:
                    message = await self._websocket.recv()
                    data = json.loads(message)
                    
                    # Check for errors
                    if data.get("error_code") is not None:
                        error_msg = f"{data.get('error_code')} - {data.get('error_message')}"
                        logger.error(f"🎤 [SONIOX STT] Error: {error_msg}")
                        await self.push_error(f"Soniox error: {error_msg}")
                        # Close websocket and stop processing
                        if self._websocket:
                            try:
                                await self._websocket.close()
                            except Exception:
                                pass
                        self._websocket = None
                        self._is_speaking = False
                        break
                    
                    # Check for finished signal
                    if data.get("finished"):
                        logger.debug("🎤 [SONIOX STT] Stream finished")
                        continue
                    
                    # Parse tokens from current response
                    non_final_tokens: list[dict] = []
                    new_final_tokens: list[dict] = []
                    
                    for token in data.get("tokens", []):
                        if not token.get("text"):
                            continue
                            
                        if token.get("is_final"):
                            # Final tokens are returned once and should be appended to final_tokens
                            new_final_tokens.append(token)
                            self._final_tokens.append(token)
                        else:
                            # Non-final tokens update as more audio arrives; reset them on every response
                            non_final_tokens.append(token)
                    
                    # Update non-final tokens (replace, don't accumulate)
                    self._last_non_final_tokens = non_final_tokens
                    
                    # Log transcriptions
                    if new_final_tokens:
                        # Render all final tokens
                        final_text = self._render_tokens(self._final_tokens, [])
                        logger.success(f"🎤 [SONIOX STT] ✨ Final transcription: '{final_text.strip()}'")
                    elif non_final_tokens:
                        # Render final + non-final tokens for preview
                        preview_text = self._render_tokens(self._final_tokens, non_final_tokens)
                        logger.debug(f"🎤 [SONIOX STT] Partial transcription: '{preview_text.strip()}'")
                        
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("🎤 [SONIOX STT] WebSocket connection closed by server")
                    self._websocket = None
                    break
                except websockets.exceptions.ConnectionClosedOK:
                    # Normal, server closed after finished
                    logger.debug("🎤 [SONIOX STT] WebSocket connection closed normally")
                    self._websocket = None
                    break
                except json.JSONDecodeError as e:
                    logger.warning(f"🎤 [SONIOX STT] Failed to parse JSON: {e}")
                        
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
            self._final_tokens = []
            self._last_non_final_tokens = []
            self._current_speaker = None
            self._current_language = None
            
            # Reconnect if websocket is closed
            if self._websocket is None:
                logger.warning("🎤 [SONIOX STT] WebSocket is closed, reconnecting...")
                await self._reconnect_websocket()
            
            logger.info(f"🎤 [SONIOX STT] 🗣️  User started speaking - listening...")
            await self.push_frame(frame, direction)
            
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._is_speaking = False
            logger.info(f"🎤 [SONIOX STT] 🤐 User stopped speaking - processing...")
            # Send empty string to signal end-of-audio to Soniox (as per reference)
            if self._websocket:
                try:
                    # Empty string signals end-of-audio to the server
                    await self._websocket.send("")
                    logger.debug("🎤 [SONIOX STT] Sent end-of-audio signal to Soniox")
                except Exception as e:
                    logger.debug(f"🎤 [SONIOX STT] Could not send end-of-audio: {e}")
            
            # Wait a short time for final tokens to arrive (Soniox may send them after end-of-audio)
            await asyncio.sleep(0.5)
            
            # Extract transcription from final tokens (preferred) or non-final tokens (fallback)
            text_to_send = None
            if self._final_tokens:
                # Render final tokens
                final_text = self._render_tokens(self._final_tokens, [])
                text_to_send = self._clean_transcription(final_text)
                logger.info(f"🎤 [SONIOX STT] Using final transcription: '{text_to_send}'")
            elif self._last_non_final_tokens:
                # Fallback to non-final tokens
                partial_text = self._render_tokens([], self._last_non_final_tokens)
                text_to_send = self._clean_transcription(partial_text)
                logger.info(f"🎤 [SONIOX STT] Using partial transcription (no final received): '{text_to_send}'")
            
            if text_to_send and text_to_send.strip():
                logger.success(f"🎤 [SONIOX STT] ✨ Sending TranscriptionFrame: '{text_to_send}'")
                await self.push_frame(TranscriptionFrame(text=text_to_send.strip(), user_id="", timestamp=""), direction)
                # Trigger LLM to process the transcription
                logger.info(f"🎤 [SONIOX STT] 📤 Sending LLMRunFrame to trigger LLM")
                await self.push_frame(LLMRunFrame(), direction)
            else:
                logger.warning("🎤 [SONIOX STT] ⚠️ No transcription available to send")
            
            # Reset for next utterance
            self._final_tokens = []
            self._last_non_final_tokens = []
            
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
                except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK):
                    logger.warning("🎤 [SONIOX STT] WebSocket connection closed while sending audio")
                    self._websocket = None
                    self._is_speaking = False
                except Exception as e:
                    # Check if it's a connection-related error
                    error_str = str(e).lower()
                    if "1000" in str(e) or "closed" in error_str or "connection" in error_str:
                        logger.warning(f"🎤 [SONIOX STT] WebSocket connection issue: {e}")
                        self._websocket = None
                        self._is_speaking = False
                    else:
                        # Log other errors but don't stop processing
                        logger.error(f"❌ [SONIOX STT] Error sending audio: {e}")
            
            # Always push audio downstream
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

