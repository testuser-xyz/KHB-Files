#
# Groq LLM Service for Pipecat
# Uses Groq's free API for fast LLM responses
#
import asyncio
import os
from loguru import logger
from dotenv import load_dotenv
from groq import Groq

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesFrame,
    LLMRunFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.ai_service import AIService

load_dotenv()


class GroqLLMService(AIService):
    """
    Groq LLM service for generating intelligent responses.
    Uses Groq's free API with fast inference.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "llama-3.1-8b-instant",  # Fast and free model
        **kwargs
    ):
        super().__init__(**kwargs)
        self._api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self._api_key:
            raise ValueError("Groq API key is required. Set GROQ_API_KEY in .env file")
        
        self._model = model
        self._client = Groq(api_key=self._api_key)
        logger.info(f"🤖 [GROQ LLM] Initialized with model: {self._model}")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames and generate LLM responses."""
        await super().process_frame(frame, direction)
        
        # Process LLMMessagesFrame (from context aggregator)
        if isinstance(frame, LLMMessagesFrame):
            messages = frame.messages
            logger.info(f"🤖 [GROQ LLM] Processing {len(messages)} messages")
            
            try:
                # Convert pipecat messages format to Groq format
                groq_messages = []
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if content:
                        groq_messages.append({
                            "role": role,
                            "content": content
                        })
                
                if not groq_messages:
                    logger.warning("🤖 [GROQ LLM] No messages to process")
                    await self.push_frame(frame, direction)
                    return
                
                logger.info(f"🤖 [GROQ LLM] Calling Groq API with {len(groq_messages)} messages...")
                
                # Call Groq API asynchronously to avoid blocking
                def _call_groq_api():
                    return self._client.chat.completions.create(
                        model=self._model,
                        messages=groq_messages,
                        temperature=0.7,
                        max_tokens=512,
                        stream=False,  # Non-streaming for simplicity
                    )
                
                response = await asyncio.to_thread(_call_groq_api)
                
                # Extract response text
                response_text = response.choices[0].message.content
                logger.success(f"🤖 [GROQ LLM] ✨ Response: '{response_text[:100]}...'")
                
                # Emit response frames
                await self.push_frame(LLMFullResponseStartFrame(), direction)
                await self.push_frame(TextFrame(text=response_text), direction)
                await self.push_frame(LLMFullResponseEndFrame(), direction)
                
            except Exception as e:
                logger.error(f"❌ [GROQ LLM] Error: {e}")
                import traceback
                logger.error(f"❌ [GROQ LLM] Traceback: {traceback.format_exc()}")
                # Fallback response on error
                await self.push_frame(LLMFullResponseStartFrame(), direction)
                await self.push_frame(TextFrame(text="I apologize, but I'm having trouble processing that right now. Could you please try again?"), direction)
                await self.push_frame(LLMFullResponseEndFrame(), direction)
        elif isinstance(frame, LLMRunFrame):
            # LLMRunFrame triggers the LLM - pass it through so context aggregator can handle it
            logger.debug("🤖 [GROQ LLM] Received LLMRunFrame - waiting for LLMMessagesFrame")
            await self.push_frame(frame, direction)
        else:
            # Pass through other frames
            await self.push_frame(frame, direction)

