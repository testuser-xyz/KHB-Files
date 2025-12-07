#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import os
import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

# Import ONLY Soniox STT, Cartesia TTS, and Simple Response (NO GEMINI, NO OPENAI)
from processors import SonioxSTTService, CartesiaTTSService, SimpleResponseService

# Ensure environment variables are loaded from .env file
load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


# NOTE: This bot uses ONLY Soniox STT + Cartesia TTS
# No Gemini, no OpenAI - just simple rule-based responses
# Speech flow: User speaks → Soniox → SimpleResponse → Cartesia → User hears


async def run_bot(websocket_client):
    logger.info("🚀 Starting bot initialization (Soniox + Cartesia ONLY)...")
    
    # Verify API keys - ONLY Soniox and Cartesia needed!
    soniox_key = os.getenv("SONIOX_API_KEY")
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    
    if not soniox_key:
        raise ValueError("❌ SONIOX_API_KEY not set!")
    if not cartesia_key:
        raise ValueError("❌ CARTESIA_API_KEY not set!")
    
    logger.info("✅ API keys verified (Soniox + Cartesia)")
    logger.info("ℹ️  NO LLM API calls - using simple rule-based responses")
    
    ws_transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=ProtobufFrameSerializer(),
        ),
    )
    logger.info("✅ WebSocket transport initialized")

    # === Soniox STT (Speech to Text) ===
    logger.info("🎤 Initializing Soniox STT...")
    stt = SonioxSTTService(
        api_key=soniox_key,
        model="stt-rt-preview",
        sample_rate=16000,
    )
    logger.info("✅ Soniox STT initialized")

    # === Simple Response System (NO API CALLS) ===
    # This replaces LLM with simple pattern matching - NO Gemini, NO OpenAI!
    logger.info("💬 Initializing Simple Response System (rule-based, no API)...")
    response_system = SimpleResponseService()
    logger.info("✅ Simple Response System initialized")

    # === Cartesia TTS (Text to Speech) ===
    logger.info("🔊 Initializing Cartesia TTS...")
    tts = CartesiaTTSService(
        api_key=cartesia_key,
        voice_id="694f9389-aac1-45b6-b726-9d9369183238",  # Sonic voice
        model_id="sonic-3",
        sample_rate=16000,
    )
    logger.info("✅ Cartesia TTS initialized")

    # === ALL GEMINI CODE REMOVED ===
    # Original Gemini Live used: GeminiLiveLLMService for STT+LLM+TTS all-in-one
    # We removed it completely!
    # 
    # === ALL OPENAI CODE REMOVED ===
    # We also removed OpenAI LLM to avoid any API costs
    # 
    # NEW FLOW: Soniox (STT) → SimpleResponse (rule-based) → Cartesia (TTS)
    # NO API CALLS for text generation - just pattern matching!

    context = LLMContext(
        [
            {
                "role": "user",
                "content": "Start by greeting the user warmly and introducing yourself.",
            }
        ],
    )
    context_aggregator = LLMContextAggregatorPair(context)

    # RTVI events for Pipecat client UI
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    logger.info("🔧 Building pipeline: WebSocket → Soniox STT → SimpleResponse → Cartesia TTS → WebSocket")
    logger.info("ℹ️  Pipeline uses ZERO external LLM APIs (no Gemini, no OpenAI)")
    pipeline = Pipeline(
        [
            ws_transport.input(),       # WebSocket audio input
            stt,                        # Soniox STT: audio -> text
            context_aggregator.user(),  # Add user text to context
            rtvi,                       # RTVI events
            response_system,            # SimpleResponse: text -> response text (NO API!)
            tts,                        # Cartesia TTS: text -> audio
            context_aggregator.assistant(),  # Add assistant response to context
            ws_transport.output(),      # WebSocket audio output
        ]
    )
    logger.info("✅ Pipeline built successfully (100% Soniox + Cartesia)")

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info("🎉 Pipecat client ready - starting conversation...")
        await rtvi.set_bot_ready()
        # Kick off the conversation.
        await task.queue_frames([LLMRunFrame()])
        logger.info("💬 Conversation started - bot will greet user")

    @ws_transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("🔌 Pipecat Client connected - WebSocket established")

    @ws_transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("🔌 Pipecat Client disconnected - closing pipeline")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)
