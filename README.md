# Wealth Expert — goal-based voice financial planner

A real-time voice agent ("Maya") built on Pipecat that runs a goal-based financial
planning conversation like a human wealth advisor, computes every number with
deterministic Python tools, and ends by generating a financial plan PDF.

**Design rule:** the LLM never computes a number. All 9 tools own the math
([core/finmath.py](core/finmath.py), unit-tested); every tool result carries a
`narration_hint`, a `progress` checklist, and a `next_step` instruction that
re-anchors the LLM each turn.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
```

### Env vars (.env)

| Var | What |
|---|---|
| `OPENAI_API_KEY` | GPT-4o (conversation + function calling) |
| `SARVAM_API_KEY` | Sarvam TTS (and fallback STT) |
| `SARVAM_VOICE_ID` | TTS voice, default `anushka` (warm female, bulbul:v2) |
| `STT_PROVIDER` | `sarvam` (default) \| `deepgram` \| `ringg` |
| `RINGG_API_KEY` | Required for `STT_PROVIDER=ringg`; warns + falls back to Sarvam if missing |
| `DEEPGRAM_API_KEY` | Only for `STT_PROVIDER=deepgram` |

## Run

```bash
python bot.py
```

Open **http://localhost:7860** in the browser (prebuilt Pipecat client), allow the
mic, click Connect — Maya speaks first. Every tool call and result is logged to the
console (the demo debug view). The plan PDF lands in `./output/` and is served at
`http://localhost:7861/<filename>` (both printed prominently in the console).

## Tests

```bash
pytest tests/ -v   # known-answer tests for every formula
```

## Sample conversation script (demo / stage-by-stage testing)

Maya greets you and asks your name.

1. **Name** → say **"Rohan"** (the rich fixture: ₹18L across 6 funds, 2
   underperformers, ₹12K existing SIPs; "Priya" is a smaller clean portfolio;
   any other name maps to Rohan's data). Maya should flag the two dragging funds.
2. **Finances** → income *"two and a half lakhs a month"*, expenses *"one lakh
   twenty thousand"*, EMI *"thirty thousand car loan"*. Expect: strong saver,
   healthy debt, big idle surplus.
3. **Goals** → *"I want to buy a house in Pune, around one crore, in ten years"*
   and *"my daughter's education, about thirty lakhs, twelve years away"*.
   Expect the inflation reaction (house → ~2 crores at 7%, education at 10%).
4. **Risk** → answer the scenario questions, e.g. *"I'd hold, maybe top up a
   little"* / *"I'd buy more, it's an opportunity"* → aggressive; say "I'd exit"
   twice to land conservative.
5. **Gap** → Maya projects your existing corpus per goal and quotes the required
   SIP and affordability.
6. **Negotiation** (if tight) → *"I can only do fifty thousand a month"* — Maya
   reprioritizes and narrates trade-offs (shortfall % or extended horizon).
7. **Close** → agree to a number; Maya builds the portfolio, generates the PDF,
   and gives three action items. Check the console for the PDF path/URL.

## Project structure

```
bot.py                  # Pipecat pipeline assembly + dev runner entrypoint
services/ringg_stt.py   # RinggSTTService(STTService) wrapping ringglabs AsyncClient.stream
agent/prompts.py        # Maya's stage-machine system prompt + greeting kick-off
agent/tools.py          # 9 tool schemas + handlers (guard rails, console logging)
core/session.py         # SessionState + progress checklist + next_step logic
core/finmath.py         # Pure deterministic math (unit tested)
core/portfolio_data.py  # Stub "MF Central" portfolio fixtures
core/plan_pdf.py        # 2-page plan PDF (reportlab)
tests/test_finmath.py   # Known-answer pytest cases for every formula
```

Pipeline: SmallWebRTC in → STT → user context aggregator → GPT-4o (9 tools
registered) → Sarvam TTS (websocket, interruptible) → SmallWebRTC out → assistant
context aggregator. Audio in at 16kHz.
