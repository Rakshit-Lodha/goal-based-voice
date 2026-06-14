"""Wealth Expert — Maya. Pipecat pipeline assembly + development runner entrypoint.

Run:  python bot.py
Then open http://localhost:7860/client in the browser and talk.
"""

import functools
import http.server
import os
import threading

from dotenv import load_dotenv
from loguru import logger

load_dotenv(override=True)

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.base_transport import TransportParams

from agent.prompts import GREETING_INSTRUCTION, SYSTEM_PROMPT
from agent.tools import register_tools
from core import session, ui_bus

PDF_PORT = 7861

transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        # Tuned for noisy demo environments: longer stop_secs avoids chopping
        # utterances at natural pauses; higher confidence/volume ignores fans, typing.
        vad_analyzer=SileroVADAnalyzer(params=VADParams(
            confidence=0.90,
            start_secs=0.40,
            stop_secs=0.80,
            min_volume=0.75,
        )),
    ),
}


def make_stt():
    """Pluggable STT behind STT_PROVIDER: ringg | sarvam | deepgram."""
    provider = os.getenv("STT_PROVIDER", "ringg").lower()

    if provider == "ringg":
        if os.getenv("RINGG_API_KEY"):
            from services.ringg_stt import RinggSTTService
            logger.info("STT: Ringg Parrot")
            return RinggSTTService(api_key=os.environ["RINGG_API_KEY"],
                                   language=os.getenv("RINGG_LANGUAGE", "en"))
        logger.warning("STT_PROVIDER=ringg but RINGG_API_KEY is not set — "
                       "falling back to Sarvam STT.")
        provider = "sarvam"

    if provider == "deepgram":
        from pipecat.services.deepgram.stt import DeepgramSTTService
        logger.info("STT: Deepgram")
        return DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])

    from pipecat.services.sarvam.stt import SarvamSTTService
    logger.info("STT: Sarvam")
    return SarvamSTTService(api_key=os.environ["SARVAM_API_KEY"])


def serve_pdf_dir():
    """Serve ./output at http://localhost:7861 so the plan PDF has a clickable URL."""
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=out)
    try:
        server = http.server.ThreadingHTTPServer(("", PDF_PORT), handler)
    except OSError:
        return  # already running from a previous connection
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"Serving plan PDFs from {out} at http://localhost:{PDF_PORT}/")


async def run_bot(transport):
    session.reset()

    stt = make_stt()

    llm = OpenAILLMService(api_key=os.environ["OPENAI_API_KEY"], model="gpt-4o")
    tools = register_tools(llm)

    tts = SarvamTTSService(
        api_key=os.environ["SARVAM_API_KEY"],
        settings=SarvamTTSService.Settings(
            model=os.getenv("SARVAM_TTS_MODEL", "bulbul:v3"),
            voice=os.getenv("SARVAM_VOICE_ID", "anushka"),
            language="en-IN",
        ),
    )

    # RTVI: pushes live state snapshots to the browser UI over the data channel.
    rtvi = RTVIProcessor(transport=transport)
    ui_bus.bind(rtvi)

    context = LLMContext(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": GREETING_INSTRUCTION},
        ],
        tools=tools,
    )
    aggregators = LLMContextAggregatorPair(context)

    pipeline = Pipeline([
        transport.input(),
        rtvi,
        stt,
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
        observers=[RTVIObserver(rtvi)],
    )

    @rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info("Client ready — Maya speaks first")
        await rtvi.set_bot_ready()
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        ui_bus.unbind()
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    serve_pdf_dir()
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main
    main()
