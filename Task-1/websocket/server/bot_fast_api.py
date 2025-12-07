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

# Import Soniox STT, Cartesia TTS, and Groq LLM
from processors import SonioxSTTService, CartesiaTTSService, GroqLLMService

# Ensure environment variables are loaded from .env file
load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


# NOTE: This bot uses ONLY Soniox STT + Cartesia TTS
# No Gemini, no OpenAI - just simple rule-based responses
# Speech flow: User speaks → Soniox → SimpleResponse → Cartesia → User hears


async def run_bot(websocket_client):
    logger.info("🚀 Starting bot initialization (Soniox + Groq LLM + Cartesia)...")
    
    # Verify API keys - Soniox, Groq, and Cartesia needed!
    soniox_key = os.getenv("SONIOX_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    
    if not soniox_key:
        raise ValueError("❌ SONIOX_API_KEY not set!")
    if not groq_key:
        raise ValueError("❌ GROQ_API_KEY not set!")
    if not cartesia_key:
        raise ValueError("❌ CARTESIA_API_KEY not set!")
    
    logger.info("✅ API keys verified (Soniox + Groq + Cartesia)")
    logger.info("ℹ️  Using Groq LLM for intelligent responses (free tier available)")
    
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
        model="stt-rt-v3",  # Updated to v3 model (default)
        sample_rate=16000,
        audio_format="pcm_s16le",  # PCM 16-bit little-endian (Pipecat standard)
        channels=1,  # Mono audio
    )
    logger.info("✅ Soniox STT initialized")

    # === Groq LLM (Intelligent Responses) ===
    logger.info("🤖 Initializing Groq LLM...")
    llm = GroqLLMService(
        api_key=groq_key,
        model="llama-3.1-8b-instant",  # Fast and free model
    )
    logger.info("✅ Groq LLM initialized")

    # === Cartesia TTS (Text to Speech) ===
    logger.info("🔊 Initializing Cartesia TTS...")
    tts = CartesiaTTSService(
        api_key=cartesia_key,
        voice_id="694f9389-aac1-45b6-b726-9d9369183238",  # Sonic voice
        model_id="sonic-3",
        sample_rate=16000,
    )
    logger.info("✅ Cartesia TTS initialized")

    # Pipeline flow: Soniox (STT) → Groq LLM (intelligent responses) → Cartesia (TTS)
    # Groq provides fast, free LLM responses

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

    logger.info("🔧 Building pipeline: WebSocket → Soniox STT → Groq LLM → Cartesia TTS → WebSocket")
    logger.info("ℹ️  Pipeline uses Groq LLM for intelligent responses")
    pipeline = Pipeline(
        [
            ws_transport.input(),       # WebSocket audio input
            stt,                        # Soniox STT: audio -> text
            context_aggregator.user(),  # Add user text to context
            rtvi,                       # RTVI events
            llm,                        # Groq LLM: text -> intelligent response
            tts,                        # Cartesia TTS: text -> audio
            context_aggregator.assistant(),  # Add assistant response to context
            ws_transport.output(),      # WebSocket audio output
        ]
    )
    logger.info("✅ Pipeline built successfully (Soniox + Groq + Cartesia)")

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
