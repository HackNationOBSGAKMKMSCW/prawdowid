import type { AnalysisCardView } from '../lib/result.ts';

export default function AnalysisCard({ card }: { card: AnalysisCardView }) {
  return (
    <article className="analysis-card" data-tone={card.tone}>
      <div className="analysis-card__head">
        <span className="dot dot--md" aria-hidden="true">
          {card.icon}
        </span>
        <h2 className="analysis-card__title">{card.title}</h2>
      </div>
      {card.quote && <p className="analysis-card__quote">„{card.quote}”</p>}
      <p className="analysis-card__body">{card.body}</p>
      {card.source && <span className="analysis-card__source">Źródło: {card.source}</span>}
    </article>
  );
}
