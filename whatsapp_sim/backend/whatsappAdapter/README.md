# WhatsApp adapter (demo)

A demonstration channel for SprawdzTo: users talk to a **SprawdzTo** contact in a
WhatsApp-style chat, send a phrase, question, or forwarded message, and get back
a fact-check verdict with sources.

The adapter speaks the **WhatsApp Cloud API** formats: it accepts webhook
payloads (`object: whatsapp_business_account`) and answers with the message
bodies that `POST /{phone-number-id}/messages` expects. In this repository the
"WhatsApp" side is the browser simulator at `/whatsapp`. Connecting a real
WhatsApp Business number would only need a transport that forwards Meta's
webhooks here and posts the returned messages to the Graph API.

```
simulator (/whatsapp) ──webhook──▶ POST /api/whatsapp/webhook
                                     │ SprawdzToBot
                                     │  ├─ textAnalysis.run(text)    → statements
                                     │  └─ apiReading.run(analysis)  → fact checks
                      ◀──messages──  └─ formatting: verdict, sources, caveats
```

## Run

From the repository root (Python 3.14):

```bash
.venv/bin/python -m pip install -r backend/whatsappAdapter/requirements.txt
cd backend && ../.venv/bin/python -m whatsappAdapter --demo   # no keys needed
```

Then start the frontend (`cd frontend && npm run dev`) and open
<http://localhost:5173/whatsapp>. Vite proxies `/api` to port 8000.

- `--demo` answers from a few built-in example topics (vaccines and autism, 5G
  and coronavirus, the Great Wall, boiling water). Every demo reply is labelled
  as example data.
- Without `--demo` the adapter runs the real pipeline and needs
  `FREELLM_API_KEY` (plus `FREELLM_BASE_URL`, `FREELLM_MODEL`) and
  `GOOGLE_FACT_CHECK_API_KEY` in `backend/.env`. Missing keys are reported in
  the chat instead of failing silently.
- `SPRAWDZTO_MODE=demo|live`, `--host`, and `--port` are also supported.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/whatsapp/health` | `{"status": "ok", "mode": "live" \| "demo"}` |
| `POST` | `/api/whatsapp/webhook` | Cloud API webhook in, `{"messages": [...]}` out |

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
- Replies longer than WhatsApp's 4096-character limit are split.
- Message text is never printed to the console; only message IDs and timings.

## Tests

```bash
.venv/bin/python -m pytest backend/whatsappAdapter
```
