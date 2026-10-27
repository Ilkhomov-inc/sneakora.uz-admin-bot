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
- **access.py** — closed-access system. `AccessMiddleware` is attached (in `main.py`) as an outer middleware to the work router from `handlers.py`, so every handler there is reachable only by `ADMIN_IDS`, `ALLOWED_USERS` (both from `.env`) or users approved at runtime. Unknown users get an "apply" button; requests go to all admins with approve/reject buttons; admins manage approved users via `/users`. The access router is included *before* the work router and is not gated. Approved/pending users persist in `data/access.json` (git-ignored, excluded from the deploy rsync so it survives redeploys).
- **handlers.py** — the work `Router` (no access checks of its own; see access.py).
  - Photos: albums are deduplicated by `media_group_id` via an in-process dict so only the first photo hits the AI; the caption is passed as a hint (sizes, gender, price).
  - After each generation, the sneaker fields + `last_post` + `photo_file_id` are stored in FSM state (`MemoryStorage`, so lost on restart). The `set_price` callback enters `FormStates.waiting_for_price`; the next text message is routed from `handle_text` to `process_price_input`, which rebuilds the post from FSM data and re-sends it. Because state holds only the *last* post per user, pressing a button on an older post acts on the latest one.
  - `copy_text` resends the post inside a Markdown code block for one-tap copying on mobile.

## Deployment

Runs on a Google Cloud Compute Engine VM `sneakora-bot` (project `sneakora-admin-bot`, zone `us-central1-a`) as the systemd service `sneakora-bot`, code in `/opt/sneakora-bot`. To redeploy, upload the repo (including `.env`, excluding `venv`/`.git`) and run `sudo bash deploy/setup.sh` from the uploaded directory on the VM. Logs: `gcloud compute ssh sneakora-bot --command "sudo journalctl -u sneakora-bot -f"`.
