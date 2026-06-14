"""Own FastAPI app hosting the Wealth Expert voice bot + serving plan PDFs.

One port for everything: WebRTC signaling (POST /api/offer), the generated
plan PDFs (GET /output/...), and a health check. The React client (Vite, port
5173 in dev) connects here over WebRTC; live plan state streams back to it via
RTVI server messages emitted from the tools.

Run:  python server.py     (or: uvicorn server:app --port 8000)
"""

import asyncio
import os

from dotenv import load_dotenv
from loguru import logger

load_dotenv(override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from bot import run_bot
from core import consent

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Wealth Expert")

# Dev: Vite serves the UI from a different origin, so allow it to call /api/offer.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated plan PDFs at /output/<file>.
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

_webrtc = SmallWebRTCRequestHandler()


def _params() -> TransportParams:
    # Tuned for noisy demo environments: longer stop_secs avoids chopping
    # utterances at natural pauses; higher confidence/volume ignores fans, typing.
    return TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(params=VADParams(
            confidence=0.90,
            start_secs=0.40,
            stop_secs=0.80,
            min_volume=0.75,
        )),
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/offer")
async def offer(request: dict):
    """WebRTC signaling: take the browser's SDP offer, spin up the bot, return the answer."""

    async def on_connection(connection: SmallWebRTCConnection):
        transport = SmallWebRTCTransport(webrtc_connection=connection, params=_params())
        # run_bot blocks until the call ends; run it alongside this request.
        asyncio.create_task(run_bot(transport))

    answer = await _webrtc.handle_web_request(
        SmallWebRTCRequest.from_dict(request), on_connection
    )
    return answer


@app.post("/api/otp")
async def otp(request: dict):
    """Simple browser-entered OTP bridge for mocked MF Central / Finvu consent."""
    accepted = await consent.submit_otp(str(request.get("request_id", "")), str(request.get("otp", "")))
    return {"accepted": accepted}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Wealth Expert API on http://localhost:{port} (UI dev server: http://localhost:5173)")
    uvicorn.run(app, host="0.0.0.0", port=port)
