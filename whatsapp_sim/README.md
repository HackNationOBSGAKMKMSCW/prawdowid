# whatsapp_sim — SprawdzTo on WhatsApp (demo)

A demonstration channel for SprawdzTo: users talk to a **SprawdzTo** contact in a
WhatsApp-style chat, send a phrase, question, or forwarded message, and get back
a fact-check verdict with sources.

The Python adapter lives in this folder and reuses the main app's
`textAnalysis` and `apiReading` packages from `backend/`. The chat simulator
is part of the main web app: it is the **WhatsApp** view of `frontend/`
(`/whatsapp`, source in `frontend/src/whatsapp/`), next to the website view.

```
whatsapp_sim/
├── backend/                  # Python adapter (FastAPI), port 8000
│   ├── requirements.txt
│   ├── pytest.ini
│   └── whatsappAdapter/      # bot, Cloud API shapes, verdicts, server, tests
frontend/src/whatsapp/        # chat simulator, the /whatsapp view of the main app
```

The adapter speaks the **WhatsApp Cloud API** formats: it accepts webhook
payloads (`object: whatsapp_business_account`) and answers with the message
bodies that `POST /{phone-number-id}/messages` expects. Here the "WhatsApp"
side is the browser simulator. Connecting a real WhatsApp Business number would
only need a transport that forwards Meta's webhooks here and posts the returned
messages to the Graph API.

```
simulator ──webhook──▶ POST /api/whatsapp/webhook
                         │ SprawdzToBot
                         │  ├─ textAnalysis.run(text)    → statements
                         │  └─ apiReading.run(analysis)  → fact checks
          ◀──messages──  └─ formatting: verdict, sources, caveats
```

## Run

Backend (Python 3.14), from the repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r whatsapp_sim/backend/requirements.txt
cd whatsapp_sim/backend && ../../.venv/bin/python -m whatsappAdapter --demo
```

Web app with the simulator, in a second terminal:

```bash
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173/whatsapp> (or use the **Strona / WhatsApp** switch at
the top). Vite proxies `/api` to the adapter on port 8000. The WhatsApp number on
the start page opens this view with the typed message ready to send
(`/whatsapp?text=…`); nothing goes to the real WhatsApp.

- `--demo` answers from a few built-in example topics (vaccines and autism, 5G
  and coronavirus, the Great Wall, boiling water). Every demo reply is labelled
  as example data.
- Without `--demo` the adapter runs the real pipeline and needs
  `FREELLM_API_KEY` (plus `FREELLM_BASE_URL`, `FREELLM_MODEL`) and
  `GOOGLE_FACT_CHECK_API_KEY` in `backend/.env` (the main app's file). Missing
  keys are reported in the chat instead of failing silently.
- `SPRAWDZTO_MODE=demo|live`, `--host`, and `--port` are also supported.

## Simulator

- WhatsApp-style chat: message ticks, "pisze…" (typing) indicator, reply
  buttons, WhatsApp formatting (`*bold*`, `_italic_`, `~strike~`, links),
  light and dark themes, full screen on phones. History is kept in
  localStorage.
- Forwarded messages: the paperclip opens a menu to insert a sample chain
  message or send the draft as forwarded (`context.forwarded` in the
  webhook). The bot adds a chain-message warning to its answer.
- Live progress: while a message is checked, the chat shows the steps
  streamed by the adapter (analysis, fact-check search) instead of plain
  typing dots.
- Verdict card: the answer starts with a card coloured by the verdict and an
  "Otwórz źródło" button, followed by the detailed sources.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/whatsapp/health` | `{"status": "ok", "mode": "live" \| "demo"}` |
| `POST` | `/api/whatsapp/webhook` | Cloud API webhook in, `{"messages": [...]}` out |
| `POST` | `/api/whatsapp/webhook?stream=true` | Same, as NDJSON: `status` events while checking, then `messages` |

Supported incoming message types: `text`, `interactive` (`button_reply`,
`list_reply`), `button`, and `request_welcome` (sent by the simulator when the
chat opens). Other types get a "text only" reply.

## Bot behaviour

- `start`, greetings → welcome message plus reply buttons with examples.
- `pomoc` / `help` → how it works.
- Any other text (8+ characters) → analysis and fact-check search. Messages
  without extractable statements (often plain questions) are searched as a
  whole with `apiReading.run_full_text`.
- Ratings from fact-checkers are mapped to false / misleading / true /
  unverified (`verdicts.py`) and combined into one headline verdict; true and
  false ratings together are reported as conflicting.
- When a linked review is found, the reply starts with an interactive
  `cta_url` message (verdict header, checked statement with the most
  relevant rating, review-count footer, source link button); the detailed
  text follows. This is a real Cloud API message type.
- Forwarded messages (`context.forwarded` / `frequently_forwarded`) get a
  chain-message warning.
- Status lines from the streaming endpoint are a simulator feature; on real
  WhatsApp they would be ordinary messages or the typing indicator.
- Replies longer than WhatsApp's 4096-character limit are split.
- Message text is never printed to the console; only message IDs and timings.

## Checks

```bash
cd whatsapp_sim/backend && ../../.venv/bin/python -m pytest
cd frontend && npm run build && npm run lint
```
