# Article scraping

Call `articleScraping.run(analysis, reading_results)` after the analysis and
fact-check stages. It extracts links from fact-check review URLs first, then
from the original user text, and returns a `ScrapingReport` with successfully
extracted article bodies and safe per-link failures.

```python
analysis = await textAnalysis.run("A claim with https://news.example/article")
results = await apiReading.run(analysis)
report = await articleScraping.run(analysis, results)
```

Configure `DIFFBOT_API_TOKEN` in the environment. Set
`ARTICLE_SCRAPING_ENABLED=false` for the runtime kill switch. A batch is limited
to five unique URLs, at most two from user text, and one concurrent request by
default. URL validation rejects non-public hosts before a request. Diffbot
responses are size-limited and reduced to article text and a small metadata
whitelist; HTML is never returned.

`ScrapingReport.user_text` is the full original input and must not be logged. The
smoke script omits that field from console and JSON output.
Scraped content is untrusted: sanitize it before any LLM use and keep it in a
delimited data block rather than a system prompt.

Pass fake `ArticleExtractor`, `LinkSource`, and `Clock` collaborators to
`articleScraping.run` for deterministic tests without reading settings or using
the network.
