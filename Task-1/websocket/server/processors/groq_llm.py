#
# Groq LLM Service for Pipecat
# Uses Groq's free API for fast LLM responses
#
import asyncio
import hashlib
import os
from loguru import logger
from dotenv import load_dotenv
from groq import Groq

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TranscriptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesFrame,
    LLMRunFrame,
    LLMContextFrame,
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
        self._pending_transcription = None  # Store transcription until LLMRunFrame arrives
        self._conversation_history = []  # Store conversation history
        self._last_llm_run_frame = None  # Track when LLMRunFrame was received
        self._processed_message_hashes = set()  # Track processed message content hashes to avoid duplicates
        self._last_context_message_count = 0  # Track context size to detect new messages
        logger.info(f"🤖 [GROQ LLM] Initialized with model: {self._model}")
    

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames and generate LLM responses."""
        # Only log frames relevant to LLM processing (skip audio frames to reduce log spam)
        if isinstance(frame, (TranscriptionFrame, LLMRunFrame, LLMMessagesFrame, LLMContextFrame, TextFrame)):
            frame_type = type(frame).__name__
            logger.info(f"🤖 [GROQ LLM] 📥 Received {frame_type}")
        
        await super().process_frame(frame, direction)
        
        # Process LLMMessagesFrame (from context aggregator) - PRIMARY PATH
        if isinstance(frame, LLMMessagesFrame):
            messages = frame.messages
            logger.info(f"🤖 [GROQ LLM] Processing {len(messages)} messages from context aggregator")
            
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
                
                # Use helper method to process messages
                await self._process_messages(messages, direction)
                
            except Exception as e:
                logger.error(f"❌ [GROQ LLM] Error: {e}")
                import traceback
                logger.error(f"❌ [GROQ LLM] Traceback: {traceback.format_exc()}")
                # Fallback response on error
                await self.push_frame(LLMFullResponseStartFrame(), direction)
                await self.push_frame(TextFrame(text="I apologize, but I'm having trouble processing that right now. Could you please try again?"), direction)
                await self.push_frame(LLMFullResponseEndFrame(), direction)
        
        # Handle TranscriptionFrame - store it for when LLMRunFrame arrives
        elif isinstance(frame, TranscriptionFrame):
            user_text = frame.text or ""
            if user_text.strip():
                self._pending_transcription = user_text.strip()
                logger.info(f"🤖 [GROQ LLM] 📝 Stored transcription: '{self._pending_transcription}'")
            # Always pass through TranscriptionFrame
            await self.push_frame(frame, direction)
        
        # Handle LLMRunFrame - trigger LLM processing
        # Note: If aggregator doesn't emit LLMMessagesFrame, we'll process directly
        elif isinstance(frame, LLMRunFrame):
            logger.info("🤖 [GROQ LLM] ✅ Received LLMRunFrame")
            self._last_llm_run_frame = frame
            # Pass through - aggregator should emit LLMMessagesFrame or LLMContextFrame
            # We'll process messages when LLMContextFrame arrives
            await self.push_frame(frame, direction)
        
        # Handle LLMContextFrame - extract messages and process
        # The aggregator emits LLMContextFrame, but we need LLMMessagesFrame
        # So we'll extract messages from context and process them
        elif isinstance(frame, LLMContextFrame):
            logger.info("🤖 [GROQ LLM] 📋 Received LLMContextFrame")
            
            # Try to extract messages from context frame
            try:
                messages = None
                
                # Method 1: Try context.messages
                if hasattr(frame, 'context'):
                    context_obj = frame.context
                    if hasattr(context_obj, 'messages'):
                        try:
                            messages = context_obj.messages
                            if messages:
                                logger.info(f"🤖 [GROQ LLM] ✅ Extracted {len(messages)} messages from context.messages")
                        except:
                            pass
                
                # Method 2: Try context.get_messages()
                if not messages and hasattr(frame, 'context'):
                    context_obj = frame.context
                    if hasattr(context_obj, 'get_messages'):
                        try:
                            messages = context_obj.get_messages()
                            if messages:
                                logger.info(f"🤖 [GROQ LLM] ✅ Extracted {len(messages)} messages from context.get_messages()")
                        except:
                            pass
                
                # Method 3: Try direct frame.messages
                if not messages and hasattr(frame, 'messages'):
                    try:
                        messages = frame.messages
                        if messages:
                            logger.info(f"🤖 [GROQ LLM] ✅ Extracted {len(messages)} messages from frame.messages")
                    except:
                        pass
                
                # If we have messages, check if there's a new user message to process
                if messages and isinstance(messages, list) and len(messages) > 0:
                    # Check if context has grown (new message added) OR if we haven't processed anything yet
                    context_grown = len(messages) > self._last_context_message_count
                    last_msg = messages[-1] if isinstance(messages[-1], dict) else {}
                    last_role = last_msg.get('role', '') if isinstance(last_msg, dict) else ''
                    last_content = last_msg.get('content', '') if isinstance(last_msg, dict) else ''
                    
                    # Create a hash of the last message content to track if we've processed it
                    last_content_hash = hashlib.md5(f"{last_role}:{last_content}".encode()).hexdigest()
                    already_processed = last_content_hash in self._processed_message_hashes
                    
                    # Process if:
                    # 1. Last message is from user AND has content
                    # 2. We haven't processed this exact message before
                    # 3. Either context grew (new message) OR we received LLMRunFrame (new transcription)
                    if last_role == 'user' and last_content:
                        if not already_processed and (context_grown or self._last_llm_run_frame):
                            logger.info(f"🤖 [GROQ LLM] ✨ Processing user message: '{last_content[:80]}...'")
                            await self._process_messages(messages, direction)
                            self._processed_message_hashes.add(last_content_hash)
                            self._last_context_message_count = len(messages)
                            self._last_llm_run_frame = None  # Clear the flag after processing
                        elif already_processed:
                            logger.debug(f"🤖 [GROQ LLM] Skipping: already_processed=True, content='{last_content[:50]}...'")
                        else:
                            logger.debug(f"🤖 [GROQ LLM] Waiting for context growth or LLMRunFrame (context_grown={context_grown}, has_llm_run={self._last_llm_run_frame is not None})")
                    elif last_role != 'user':
                        logger.debug(f"🤖 [GROQ LLM] Skipping: last message is not from user (role={last_role})")
                    elif not last_content:
                        logger.debug(f"🤖 [GROQ LLM] Skipping: last message has no content")
                elif not messages:
                    logger.warning(f"🤖 [GROQ LLM] ⚠️ Could not extract messages from LLMContextFrame")
                    # Fallback: If we have a pending transcription, use it directly
                    if self._pending_transcription:
                        logger.info(f"🤖 [GROQ LLM] 🔄 Fallback: Processing stored transcription: '{self._pending_transcription}'")
                        # Build messages with conversation history
                        fallback_messages = []
                        if not self._conversation_history:
                            fallback_messages.append({
                                "role": "system",
                                "content": "You are a helpful and friendly assistant. Keep your responses concise and natural for voice conversation."
                            })
                        fallback_messages.extend(self._conversation_history)
                        fallback_messages.append({
                            "role": "user",
                            "content": self._pending_transcription
                        })
                        await self._process_messages(fallback_messages, direction)
                        self._pending_transcription = None
                        
            except Exception as e:
                logger.error(f"❌ [GROQ LLM] Error processing LLMContextFrame: {e}")
                import traceback
                logger.error(f"❌ [GROQ LLM] Traceback: {traceback.format_exc()}")
            
            await self.push_frame(frame, direction)
        else:
            # Pass through all other frames
            await self.push_frame(frame, direction)
    
    async def _process_messages(self, messages: list, direction: FrameDirection):
        """Helper method to process messages and generate LLM response."""
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
                return
            
            logger.info(f"🤖 [GROQ LLM] Calling Groq API with {len(groq_messages)} messages...")
            logger.debug(f"🤖 [GROQ LLM] Messages: {groq_messages}")
            
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
            
            # Update conversation history for context
            # Extract user and assistant messages from the input
            for msg in messages:
                if isinstance(msg, dict):
                    role = msg.get('role', '')
                    content = msg.get('content', '')
                    if role in ['user', 'assistant'] and content:
                        # Only add if not already in history (avoid duplicates)
                        if not any(h.get('content') == content for h in self._conversation_history):
                            self._conversation_history.append({"role": role, "content": content})
            
            # Add the assistant response
            if response_text:
                self._conversation_history.append({"role": "assistant", "content": response_text})
            
            # Keep last 20 messages (10 exchanges)
            if len(self._conversation_history) > 20:
                self._conversation_history = self._conversation_history[-20:]
            
            # Emit response frames
            await self.push_frame(LLMFullResponseStartFrame(), direction)
            await self.push_frame(TextFrame(text=response_text), direction)
            await self.push_frame(LLMFullResponseEndFrame(), direction)
                
        except Exception as e:
            logger.error(f"❌ [GROQ LLM] Error processing messages: {e}")
            import traceback
            logger.error(f"❌ [GROQ LLM] Traceback: {traceback.format_exc()}")
            # Fallback response on error
            await self.push_frame(LLMFullResponseStartFrame(), direction)
            await self.push_frame(TextFrame(text="I apologize, but I'm having trouble processing that right now. Could you please try again?"), direction)
            await self.push_frame(LLMFullResponseEndFrame(), direction)

