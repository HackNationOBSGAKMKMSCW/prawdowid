"""Public entry point for extracting article text from discovered links."""

from .models import ArticleFailure, ScrapedArticle, ScrapingReport
from .service import run

__all__ = ["run", "ArticleFailure", "ScrapedArticle", "ScrapingReport"]
