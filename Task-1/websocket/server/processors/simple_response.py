"""
Simple Rule-Based LLM Replacement
No API calls - just pattern matching for responses
"""
import re
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    TextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.ai_service import AIService


class SimpleResponseService(AIService):
    """
    A simple rule-based response system.
    No LLM API calls - just matches patterns and returns predefined responses.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info("💬 [SimpleResponse] Initialized - No API calls needed!")
        
        # Define response patterns (lowercase for matching)
        self._responses = {
            # Greetings
            r'\b(hello|hi|hey|greetings)\b': [
                "Hello! Nice to hear from you!",
                "Hi there! How can I help you today?",
                "Hey! What's on your mind?",
            ],
            
            # How are you
            r'\b(how are you|how\'s it going|what\'s up)\b': [
                "I'm doing great, thanks for asking!",
                "I'm functioning perfectly! How about you?",
                "All systems running smoothly!",
            ],
            
            # Name questions
            r'\b(what\'s your name|who are you|your name)\b': [
                "I'm your AI assistant, powered by Soniox and Cartesia!",
                "I'm an AI voice assistant here to help you.",
            ],
            
            # Help/assistance
            r'\b(help|assist|support)\b': [
                "I'm here to help! Just speak naturally and I'll respond.",
                "Sure, I can assist you! What do you need?",
            ],
            
            # Thank you
            r'\b(thank you|thanks|appreciate)\b': [
                "You're welcome!",
                "Happy to help!",
                "Anytime!",
            ],
            
            # Goodbye
            r'\b(bye|goodbye|see you|farewell)\b': [
                "Goodbye! Have a great day!",
                "See you later!",
                "Take care!",
            ],
            
            # Weather (example - not functional)
            r'\b(weather|temperature|forecast)\b': [
                "I don't have access to weather data, but I hope it's nice where you are!",
            ],
            
            # Time
            r'\b(time|what time|clock)\b': [
                "I don't have access to real-time information, but you can check your device!",
            ],
            
            # Default fallback
            None: [
                "That's interesting! Tell me more.",
                "I understand. What else would you like to know?",
                "Got it! Anything else on your mind?",
                "Interesting point! Continue.",
            ]
        }
        
        self._response_index = {}  # Track which response variant to use next

    def _get_response(self, text: str) -> str:
        """Match user input to a response pattern."""
        text_lower = text.lower().strip()
        
        # Try to match patterns
        for pattern, responses in self._responses.items():
            if pattern is None:
                continue
                
            if re.search(pattern, text_lower):
                # Rotate through responses for variety
                if pattern not in self._response_index:
                    self._response_index[pattern] = 0
                
                idx = self._response_index[pattern]
                response = responses[idx]
                
                # Move to next response for next time
                self._response_index[pattern] = (idx + 1) % len(responses)
                
                logger.info(f"💬 [SimpleResponse] Matched pattern: {pattern}")
                return response
        
        # No match - use default
        default_responses = self._responses[None]
        if None not in self._response_index:
            self._response_index[None] = 0
        
        idx = self._response_index[None]
        response = default_responses[idx]
        self._response_index[None] = (idx + 1) % len(default_responses)
        
        logger.info(f"💬 [SimpleResponse] No pattern match - using default")
        return response

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames and generate responses."""
        await super().process_frame(frame, direction)
        
        # Look for text frames (from STT)
        if isinstance(frame, TextFrame):
            user_text = frame.text
            logger.info(f"💬 [SimpleResponse] User said: '{user_text}'")
            
            # Generate response
            response_text = self._get_response(user_text)
            logger.info(f"💬 [SimpleResponse] Responding: '{response_text}'")
            
            # Emit response frames (same format as LLM)
            await self.push_frame(LLMFullResponseStartFrame(), direction)
            await self.push_frame(TextFrame(text=response_text), direction)
            await self.push_frame(LLMFullResponseEndFrame(), direction)
        else:
            # Pass through other frames
            await self.push_frame(frame, direction)
