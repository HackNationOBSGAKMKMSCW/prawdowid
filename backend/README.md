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
providers. Run the packages directly from Python; no web server is needed:
execute the host application from `backend/` or put that directory on
`PYTHONPATH`.

```python
import asyncio

import apiReading
import textAnalysis


async def main() -> None:
    analysis = await textAnalysis.run("A written claim to verify.")
    results = await apiReading.run(analysis)
    print(analysis.category, results)


asyncio.run(main())
```
