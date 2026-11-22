# whatsapp_sim — SprawdzTo on WhatsApp (demo)

A demonstration channel for SprawdzTo: users talk to a **SprawdzTo** contact in a
WhatsApp-style chat, send a phrase, question, or forwarded message, and get back
a fact-check verdict with sources.

The Python adapter lives in this folder, but it is **part of the main backend**:
`backend/server.py` serves `/api/whatsapp/*` next to `/api/check`, on the same port.
A WhatsApp message goes through **the same verification as the website**
(`backend/verification` → `api_adapter.to_check_response`). The bot gets the same
claims, verdicts, explanations, sources and manipulation/date checks, and sends them as
chat messages. The chat simulator is the **WhatsApp** view of `frontend/` (`/whatsapp`,
source in `frontend/src/whatsapp/`), next to the website view.

```
whatsapp_sim/
├── backend/                  # Python adapter (FastAPI router, included in server:app)
│   ├── pytest.ini
│   └── whatsappAdapter/      # bot, Cloud API shapes, formatting, router, tests
frontend/src/whatsapp/        # chat simulator, the /whatsapp view of the main app
```

The adapter speaks the **WhatsApp Cloud API** formats: it accepts webhook
payloads (`object: whatsapp_business_account`) and answers with the message
bodies that `POST /{phone-number-id}/messages` expects. Here the "WhatsApp"
side is the browser simulator. Connecting a real WhatsApp Business number would
only need a transport that forwards Meta's webhooks here and posts the returned
messages to the Graph API.

```
simulator ──webhook──▶ POST /api/whatsapp/webhook   (server:app, port 8000)
                         │ SprawdzToBot
                         │  ├─ admin monitor: blocks, high-risk content (panel admina)
                         │  ├─ verification.start(text)  ← the same as GET /api/check
                         │  │    claims → fact checks, trusted sites, articles
                         │  │    → manipulation/dates + verdict per claim + known disinfo
                         │  └─ CheckResponse → WhatsApp card + details
          ◀──messages──  └─ admin monitor: result, info gaps, alerts
```

## Run

From the repository root (Python 3.14):

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=backend:analysis:analysis/src .venv/bin/uvicorn server:app --port 8000
```

Web app with the simulator, in a second terminal:

```bash
cd frontend && npm install && npm run dev:live
```

Open <http://localhost:5173/whatsapp> (or use the **Strona / WhatsApp** switch at
the top). Vite proxies all of `/api` to port 8000. The WhatsApp number on the start page
opens this view with the typed message ready to send (`/whatsapp?text=…`); nothing goes
to the real WhatsApp.

Modes (`SPRAWDZTO_MODE` in the project-root `.env`):

- `live` (default): the website's verification. It needs the same keys as the website
  (`FREELLM_*`, `GOOGLE_FACT_CHECK_API_KEY`, `DATABASE_URL`, see `.env.example`) and
  takes as long (`CHECK_TIMEOUT_SECONDS`, default 360 s).
- `factcheck`: Google Fact Check only, without the model's verdict. Faster, but it can
  differ from the website.
- `demo`: a few built-in example topics (vaccines and autism, 5G and coronavirus, the
  Great Wall, boiling water), without network or keys. Every demo reply is labelled.

`WHATSAPP_ENABLED=false` turns the channel off in `server:app`.

### Standalone adapter (offline demo)

Without a database or model keys, the adapter can still run on its own:

```bash
cd whatsapp_sim/backend && ../../.venv/bin/python -m whatsappAdapter --demo   # port 8001
```

and in the project-root `.env`: `WHATSAPP_PROXY_TARGET=http://127.0.0.1:8001`.

## Simulator

- WhatsApp-style chat: message ticks, "pisze…" (typing) indicator, reply
  buttons, WhatsApp formatting (`*bold*`, `_italic_`, `~strike~`, links),
  light and dark themes, full screen on phones. History is kept in
  localStorage.
- Forwarded messages: the paperclip opens a menu to insert a sample chain
  message or send the draft as forwarded (`context.forwarded` in the
  webhook). The bot adds a chain-message warning to its answer.
- Live progress: while a message is checked, the chat shows the steps
  streamed by the adapter (analysis, then assessing the claims) instead of plain
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
- Any other text (8+ characters) → the website's verification. A message without
  extractable statements (often a plain question) is checked as one claim, as on the
  website. A bare link is validated like on the website (public HTTP(S) only).
- Verdicts and labels are the website's: Potwierdzone, Fałszywe, Wprowadzające w błąd,
  Brak wystarczających dowodów, Nie podlega weryfikacji (`verified_formatting.py`).
  Different verdicts for different claims are shown as "Różne oceny twierdzeń".
- When a claim has a linked source, the reply starts with an interactive
  `cta_url` message (verdict header, the claim with its explanation, source-count
  footer, source link button); the details follow: every claim with its verdict,
  explanation and sources, then manipulation techniques and date issues.
  This is a real Cloud API message type.
- Each message is logged in the admin panel (`admin_bridge.py`) with the website's
  verdicts, so the panel sees info gaps and alerts from WhatsApp.
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
