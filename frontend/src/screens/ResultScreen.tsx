import { useCallback, useMemo, useState } from 'react';
import { deleteCheck, reportCheck } from '../api/client.ts';
import type { CheckResult } from '../api/types.ts';
import AnalysisCard from '../components/AnalysisCard.tsx';
import ClaimCard from '../components/ClaimCard.tsx';
import { useAnnounce } from '../lib/announce.ts';
import { useChecker } from '../lib/checker.ts';
import { buildResultView } from '../lib/result.ts';
import { shareLink } from '../lib/share.ts';
import { useSpeech } from '../lib/useSpeech.ts';

type ActionState = 'idle' | 'busy' | 'done';

export default function ResultScreen({ result }: { result: CheckResult }) {
  const { input, goStart } = useChecker();
  const announce = useAnnounce();
  const view = useMemo(() => buildResultView(result), [result]);

  const [copied, setCopied] = useState(false);
  const [reported, setReported] = useState<ActionState>('idle');
  const [deleted, setDeleted] = useState<ActionState>('idle');

  const onSpeechUnsupported = useCallback(
    () => announce('Twoja przeglądarka nie umie czytać na głos.'),
    [announce],
  );
  const speech = useSpeech(onSpeechUnsupported);

  const onShare = async () => {
    const ok = await shareLink(input);
    if (ok) {
      setCopied(true);
      announce('Link skopiowany.');
    } else {
      announce('Nie udało się skopiować linku.');
    }
  };

  const onReport = async () => {
    if (reported !== 'idle') return;
    setReported('busy');
    try {
      await reportCheck(result.id);
      setReported('done');
      announce('Dziękujemy za zgłoszenie.');
    } catch {
      setReported('idle');
      announce('Nie udało się wysłać zgłoszenia. Spróbuj jeszcze raz.');
    }
  };

  const onDelete = async () => {
    if (deleted !== 'idle') return;
    setDeleted('busy');
    try {
      await deleteCheck(result.id);
      setDeleted('done');
      announce('Usunęliśmy Twoją wiadomość.');
    } catch {
      setDeleted('idle');
      announce('Nie udało się usunąć danych. Spróbuj jeszcze raz.');
    }
  };

  return (
    <div className="page page--result">
      <div className="page__head">
        <h1 className="title-l" tabIndex={-1}>
          Wynik
        </h1>
        <p className="lead">{view.summary}</p>
      </div>

      <button
        type="button"
        className="btn-outline"
        aria-pressed={speech.speaking}
        onClick={() => speech.toggle(view.readAloud)}
      >
        <span className="btn-outline__glyph" aria-hidden="true">
          {speech.speaking ? '■' : '▶'}
        </span>
        {speech.speaking ? 'Zatrzymaj' : 'Przeczytaj na głos'}
      </button>

      {view.claims.map((claim, i) => (
        <ClaimCard key={`${result.id ?? 'claim'}-${i}`} claim={claim} />
      ))}

      {view.cards.map((card) => (
        <AnalysisCard key={card.key} card={card} />
      ))}

      <p className="note note--muted">
        Wynik opiera się na wiarygodnych źródłach. Możesz je przeczytać i ocenić sam.
      </p>

      <div className="actions">
        <button
          type="button"
          className="btn-primary btn-primary--md"
          onClick={() => {
            speech.stop();
            goStart(true);
          }}
        >
          Sprawdź coś innego
        </button>
        <button type="button" className="btn-secondary" onClick={onShare}>
          {copied ? 'Skopiowano link' : 'Udostępnij wynik'}
        </button>
      </div>

      <div className="minor-actions">
        <button
          type="button"
          className="btn-link"
          onClick={onReport}
          aria-disabled={reported !== 'idle'}
        >
          {reported === 'done' ? 'Dziękujemy za zgłoszenie' : 'Zgłoś błąd'}
        </button>
        <button
          type="button"
          className="btn-link"
          onClick={onDelete}
          aria-disabled={deleted !== 'idle'}
        >
          {deleted === 'done' ? 'Dane usunięte' : 'Usuń moje dane'}
        </button>
      </div>
    </div>
  );
}
