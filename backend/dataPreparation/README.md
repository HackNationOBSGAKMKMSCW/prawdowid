# Independent analysis and reading functions

The backend exposes two asynchronous operations. Text analysis returns a
structured `AnalysisDataContainer`; API reading accepts that object and fetches
one result for each extracted statement.

```python
import asyncio

from dataPreparation import run_analysis, run_api_reading
from dataPreparation.apiReading import Category


async def check_text() -> None:
    analysis = await run_analysis("A written claim to verify.")
    reading_results = await run_api_reading(
        analysis,
        category=Category.FACT_CHECK,
        language_code="en",
    )
    print(analysis.category)
    for result in reading_results:
        print(result.request.query, result.items)


asyncio.run(check_text())
```

`analysis.category` is the topic assigned by the analyzer and is preserved in
each reading request's metadata. `Category.FACT_CHECK` selects the source type;
the Google provider does not support filtering on the analyzer's topic labels.
Set `FREELLM_API_KEY` and `GOOGLE_FACT_CHECK_API_KEY` to enable both operations.
`FREELLM_BASE_URL` and `FREELLM_MODEL` configure an OpenAI-compatible analysis
service. The API reader can also be called directly with a
`ReadingRequest` when no analyzer result is available.
