"""Live dashboards and apps (maps, measurements) that cannot be searched as text.

They are returned as "check live" links when the claim matches the source's
name, description or topics; ``articleScraping`` never downloads them.
"""

from collections.abc import Sequence

from ..models import EvidenceHit, TrustedSource
from . import SearchContext, SourceAdapter, register_adapter


@register_adapter("reference")
class ReferenceAdapter(SourceAdapter):
    async def search(
        self, sources: Sequence[TrustedSource], queries: Sequence[str], ctx: SearchContext
    ) -> list[EvidenceHit]:
        del queries, ctx
        return [
            EvidenceHit(
                source_id=source.id,
                source_name=source.name,
                trust=source.trust,
                url=source.url,
                title=source.name,
                snippet=" ".join(filter(None, [source.description, ", ".join(source.topics)])),
                kind="reference",
            )
            for source in sources
        ]
