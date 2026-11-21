# Backend

## Setup

Use Python 3.14 and install the runtime and development dependencies from the
repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m pytest
```

Copy `backend/.env.example` to `backend/.env` (or configure the same environment
variables in the runtime) to enable the language-model and Google Fact Check
providers. The two operations can also be run separately through
`POST /api/analyze` and `POST /api/check`; the latter accepts the analysis object
returned by the former.
