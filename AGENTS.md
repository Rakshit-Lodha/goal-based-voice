# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Status

"Wealth Expert" — a Pipecat voice agent (Maya) for goal-based financial planning. See README.md for setup and the demo script.

- Run: `python bot.py` (after `pip install -r requirements.txt` and filling `.env`), then open http://localhost:7860
- Test: `pytest tests/ -v`
- Architecture: SmallWebRTC → pluggable STT (`STT_PROVIDER`: sarvam/deepgram/ringg) → GPT-4o with 9 registered tools → Sarvam websocket TTS. The LLM never computes numbers; all math lives in `core/finmath.py` (unit tested) and tools in `agent/tools.py` wrap results with `narration_hint`/`progress`/`next_step` from `core/session.py`. Plan PDF rendered by `core/plan_pdf.py` into `./output/`, served on port 7861.

---

## Behavioral Guidelines

### Think Before Coding

Before implementing, state assumptions explicitly. If multiple interpretations exist, present them rather than picking silently. If a simpler approach exists, say so. If something is unclear, stop and ask.

### Simplicity First

Minimum code that solves the problem — nothing speculative. No features beyond what was asked, no abstractions for single-use code, no "flexibility" that wasn't requested, no error handling for impossible scenarios. If you write 200 lines and it could be 50, rewrite it.

### Surgical Changes

Touch only what you must. When editing existing code: don't improve adjacent code or formatting, don't refactor things that aren't broken, match existing style. Remove imports/variables/functions that your changes made unused, but don't remove pre-existing dead code unless asked. Every changed line should trace directly to the user's request.

### Goal-Driven Execution

Transform tasks into verifiable goals before starting. For multi-step tasks, state a brief plan with explicit verification steps. Strong success criteria enable independent iteration; weak criteria ("make it work") require constant clarification.
