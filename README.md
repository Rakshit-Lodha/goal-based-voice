# Wealth Expert — goal-based voice financial planner

A real-time voice agent ("Maya") built on Pipecat that runs a goal-based financial
planning conversation like a human wealth advisor, computes every number with
deterministic Python tools, and ends by generating a financial plan PDF.

**Design rule:** the LLM never computes a number. Registered tools own the math
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
| `SARVAM_VOICE_ID` | TTS voice, default `anushka` |
| `STT_PROVIDER` | `ringg` (default) \| `sarvam` \| `deepgram` |
| `RINGG_API_KEY` | Required for `STT_PROVIDER=ringg`; warns + falls back to Sarvam if missing |
| `DEEPGRAM_API_KEY` | Only for `STT_PROVIDER=deepgram` |

## Run

Backend:

```bash
.venv/bin/python server.py
```

Frontend:

```bash
cd web
npm install
npm run dev
```

Open **http://127.0.0.1:5173** in the browser, allow the mic, and click
**Start call**. The FastAPI backend runs on `http://localhost:8000`, serves PDFs
from `/output/<filename>`, and exposes the WebRTC offer endpoint at `/api/offer`.

For the mocked MF Central and Finvu consent screens, enter OTP **1234** in the
simple on-screen OTP input. OTP requests do not expire while the backend process
is alive.

## Tests

```bash
pytest tests/ -v   # known-answer tests for every formula
```

## Current conversation flow

Maya treats the caller as KYC-verified. The current demo persona is defined in
[core/session.py](core/session.py) as `Rakshit`, age `28`; Maya must not ask for
name or age.

1. **Greeting** — Maya sets the fifteen-minute agenda.
2. **Risk profile** — asks exactly two behavioral questions, then calls
   `assess_risk_profile`.
3. **Family** — captures spouse age, children with ages, and other dependents via
   `add_family`.
4. **MF Central consent and pull** — Maya must first explain why MF Central is
   needed before triggering OTP:
   - MF Central is a SEBI-regulated consolidated mutual fund portfolio view.
   - It is a joint initiative by CAMS and KFintech, formerly Karvy.
   - Pulling it lets Maya analyze holdings, check fund overlap, identify
     underperforming funds, and build a richer goal plan.
   - If the user is unsure, Maya nudges gently with safety context: encrypted
     flow, portfolio-only data, and used for this planning session.
   - Only after explicit user agreement does Maya say she is triggering the OTP
     and call `pull_mf_central` with `user_confirmed_consent: true`.
5. **Finvu Account Aggregator pull** — Maya explains that Finvu AA is
   RBI-regulated, encrypted, consent-based, and revocable. She explains that it
   can pull bank transactions, income, expenses, EMIs, EPF, NPS, and stocks, and
   that this makes cash-flow and investment analysis richer. Only after explicit
   user agreement does she trigger the OTP and call `pull_account_aggregator`.
6. **Financial snapshot confirmation** — Finvu AA returns mocked last-three-month bank
   analysis:
   - income: around one lakh fifty thousand per month
   - average monthly outflow: around ninety-five thousand
   - categories: investments, EMIs, household expenses, utilities,
     entertainment
   - holdings: EPF, NPS, and stocks
   Maya explains how the numbers were derived and asks if they are correct. AA
   data is not treated as planning-ready until the user explicitly confirms it
   or says it is good to go. If the user corrects a value, Maya calls
   `pull_account_aggregator` again with only that correction; no second OTP is
   required.
7. **Manual assets and final data gate** — before goals, Maya explicitly asks
   whether the user wants to add investments AA may not capture, such as PPF,
   FDs, gold, real estate, US stocks, or international stocks. Each mentioned
   item is recorded with `add_manual_asset`. Only after the user confirms the AA
   data and answers the additional-investments question does Maya call
   `confirm_financial_snapshot`; goals must not start before that tool succeeds.
8. **Goals** — Maya first explains the planning framework: separate safety,
   long-term independence, and personal aspirations. She then proactively
   suggests:
   - emergency fund as a default primary goal because it gives roughly six
     months of runway for job loss, medical stress, or other disruptions
   - retirement as a default primary goal anchored to age sixty because it
     protects long-term independence
   - child education if relevant from family details
   Emergency fund target is computed by `add_goal` as six months of confirmed
   monthly outflow, so the LLM still never calculates it.
9. **Gap analysis** — for each funded goal, Maya calls
   `project_existing_corpus` and `compute_gap_and_sip`.
10. **Reprioritization** — if the SIP is tight or the user pushes back, Maya
    calls `reprioritize`.
11. **Portfolio plan** — Maya explains horizon-based phasing:
    - short term: one debt-heavy phase
    - medium term: two phases, balanced then debt-heavy
    - long term: three phases, equity-heavy then balanced then debt glide-down
    She calls `build_goal_portfolio` per funded goal.
12. **Current-phase presentation** — Maya speaks only about the current phase's
    asset allocation and funds. Future phases are mentioned as glide-down
    context, not read as full fund lists. Fund rationale should reference the
    user's risk profile, goal horizon, return profile, downside protection,
    volatility, and role in the phase.
13. **Close** — Maya calls `generate_plan_pdf`, gives exactly three action
    items, and closes warmly.

## Demo notes

- MF Central and Finvu OTP are mocked with `1234`.
- MF Central uses the Rohan fixture by default: about eighteen lakhs across six
  mutual funds, two underperformers, and twelve thousand rupees of monthly SIPs.
- Finvu AA mocked assets: EPF four lakh fifty thousand, NPS fifty thousand, and
  stocks five lakhs.
- The dashboard receives live state snapshots over RTVI server messages and
  shows risk, family, MF Central, Finvu AA, goals, SIP gap, current-phase
  portfolio, and the plan PDF link.

## Project structure

```
bot.py                  # Pipecat pipeline assembly + dev runner entrypoint
server.py               # FastAPI backend for WebRTC offer, OTP bridge, PDFs
services/ringg_stt.py   # RinggSTTService(STTService) wrapping ringglabs AsyncClient.stream
agent/prompts.py        # Maya's stage-machine system prompt + greeting kick-off
agent/tools.py          # Tool schemas + handlers (guard rails, console logging)
core/session.py         # SessionState + progress checklist + next_step logic
core/consent.py         # Simple non-expiring mocked OTP bridge
core/ui_bus.py          # RTVI server-message bridge for live dashboard state
core/finmath.py         # Pure deterministic math (unit tested)
core/portfolio_data.py  # Stub "MF Central" portfolio fixtures
core/plan_pdf.py        # 2-page plan PDF (reportlab)
tests/test_finmath.py   # Known-answer pytest cases for every formula
web/                    # React dashboard + Pipecat client
```

Pipeline: SmallWebRTC in → RTVI → STT → user context aggregator → GPT-4o with
registered tools → Sarvam TTS (websocket, interruptible) → SmallWebRTC out →
assistant context aggregator. Audio in at 16kHz.
