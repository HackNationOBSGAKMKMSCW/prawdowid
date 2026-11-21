# Text analysis package

Call `textAnalysis.run(text)` to get a structured analysis object, then pass that
object to `apiReading.run(analysis)` when you want to fetch fact-check data.

```python
import asyncio

import apiReading
import textAnalysis


async def check_text() -> None:
    analysis = await textAnalysis.run("A written claim to verify.")
    reading_results = await apiReading.run(analysis)
    print(analysis.category)
    for result in reading_results:
        print(result.request.query, result.items)


asyncio.run(check_text())
```

The analysis package reads `FREELLM_API_KEY`, `FREELLM_BASE_URL`, and
`FREELLM_MODEL` from the environment. The reading package reads
`GOOGLE_FACT_CHECK_API_KEY`. The analyzer's topic and language are carried in
the analysis object and used internally by the reader. Progress and elapsed time
for sanitization, the model request, validation, and cleanup are printed to the
console; input text and credentials are not printed.
