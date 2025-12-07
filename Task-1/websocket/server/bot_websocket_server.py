#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

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
from pipecat.transports.websocket.server import (
    WebsocketServerParams,
    WebsocketServerTransport,
)

# Import Soniox STT, Cartesia TTS, and Groq LLM
from processors import SonioxSTTService, CartesiaTTSService, GroqLLMService

# NOTE: This bot uses Soniox STT + Groq LLM + Cartesia TTS
# Speech flow: User speaks → Soniox → Groq LLM → Cartesia → User hears


async def run_bot_websocket_server():
    logger.info("🚀 Starting bot initialization (WebSocket Server mode - Soniox + Groq LLM + Cartesia)...")
    
    # Verify API keys - Soniox, Groq, and Cartesia needed!
    soniox_key = os.getenv("SONIOX_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    
    if not soniox_key:
        raise ValueError("❌ SONIOX_API_KEY not set!")
    if not groq_key:
        raise ValueError("❌ GROQ_API_KEY not set! Get a free API key from https://console.groq.com/")
    if not cartesia_key:
        raise ValueError("❌ CARTESIA_API_KEY not set!")
    
    logger.info("✅ API keys verified (Soniox + Groq + Cartesia)")
    logger.info("ℹ️  Using Groq LLM for intelligent responses (free tier available)")
    
    ws_transport = WebsocketServerTransport(
        params=WebsocketServerParams(
            serializer=ProtobufFrameSerializer(),
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
            session_timeout=60 * 3,  # 3 minutes
        )
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

    # FLOW: Soniox (STT) → Groq LLM (intelligent responses) → Cartesia (TTS)
    # Groq offers free tier with generous limits for testing

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
            llm,                        # Groq LLM: text -> intelligent response text
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
        logger.info("Pipecat client ready.")
        await rtvi.set_bot_ready()
        # Kick off the conversation.
        await task.queue_frames([LLMRunFrame()])

    @ws_transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Pipecat Client connected")

    @ws_transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Pipecat Client disconnected")
        await task.cancel()

    @ws_transport.event_handler("on_session_timeout")
    async def on_session_timeout(transport, client):
        logger.info(f"Entering in timeout for {client.remote_address}")
        await task.cancel()

    runner = PipelineRunner()

    await runner.run(task)
