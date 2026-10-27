# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Telegram bot (aiogram 3) for the SNEAKORA sneaker shop. Staff send a sneaker photo or a model name; an LLM (Google Gemini or OpenAI-compatible) identifies brand/model/gender/colors and the bot replies with a channel-ready post in a fixed Russian-language template. All user-facing text, prompts, and code comments are in Russian — keep it that way.

## Commands

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill BOT_TOKEN and GEMINI_API_KEY / OPENAI_API_KEY
python3 main.py        # long polling; drops pending updates on start
```

There are no tests, linter, or build step.

## Architecture

Flat module layout; data flows `handlers.py` → `ai_service.py` → `template.py`:

- **config.py** — loads `.env` from the repo dir at import time into class attributes on `Config`; a module-level `config` singleton is imported everywhere. Settings are read once at import, so changing `.env` requires a restart.
- **ai_service.py** — `AIService` picks a provider from `AI_PROVIDER` (`gemini` | `openai`) in `__init__`; a module-level `ai_service` singleton is created on import. Both providers share one `SYSTEM_PROMPT` that demands strict JSON (`brand`, `model`, `gender_type`, `sizes`, `colors`, `price`); `clean_json_response` strips markdown fences and regex-extracts the JSON object. Gemini uses the synchronous `google-genai` SDK wrapped in `run_in_executor`; OpenAI uses `AsyncOpenAI` with `response_format=json_object` and an optional `OPENAI_BASE_URL` (e.g. OpenRouter). Adding a provider means adding `_analyze_image_*` / `_analyze_text_*` methods and branches in `analyze_image` / `analyze_text`.
- **template.py** — `SneakerData` dataclass and `format_sneaker_post`, the single source of the post format (shown in README). Price logic: an explicit price gets `$` appended unless it already has `$`/`₽`/`руб`; otherwise `PRICE_MODE=placeholder` prints `💰 Цена: ___$` and `omit` drops the line.
- **handlers.py** — single aiogram `Router`. Every handler checks `config.is_user_allowed` (empty `ALLOWED_USERS` = open access).
  - Photos: albums are deduplicated by `media_group_id` via an in-process dict so only the first photo hits the AI; the caption is passed as a hint (sizes, gender, price).
  - After each generation, the sneaker fields + `last_post` + `photo_file_id` are stored in FSM state (`MemoryStorage`, so lost on restart). The `set_price` callback enters `FormStates.waiting_for_price`; the next text message is routed from `handle_text` to `process_price_input`, which rebuilds the post from FSM data and re-sends it. Because state holds only the *last* post per user, pressing a button on an older post acts on the latest one.
  - `copy_text` resends the post inside a Markdown code block for one-tap copying on mobile.
