import { useCallback, useMemo, useState } from 'react';
import type { CheckResult } from '../api/types.ts';
import AnalysisCard from '../components/AnalysisCard.tsx';
import ClaimCard from '../components/ClaimCard.tsx';
import DeleteDialog from '../components/DeleteDialog.tsx';
import ReportDialog from '../components/ReportDialog.tsx';
import { useAnnounce } from '../lib/announce.ts';
import { useChecker } from '../lib/checker.ts';
import { buildResultView } from '../lib/result.ts';
import { shareLink } from '../lib/share.ts';
import { useSpeech } from '../lib/useSpeech.ts';

export default function ResultScreen({ result }: { result: CheckResult }) {
  const { input, goStart } = useChecker();
  const announce = useAnnounce();
  const view = useMemo(() => buildResultView(result), [result]);

  const [copied, setCopied] = useState(false);
  const [reported, setReported] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [dialog, setDialog] = useState<'report' | 'delete' | null>(null);

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
        <ClaimCard key={`${result.id ?? 'claim'}-${i}`} claim={claim} index={i} />
      ))}

      {view.cards.map((card, i) => (
        <AnalysisCard key={card.key} card={card} index={view.claims.length + i} />
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
          className="minor-action"
          data-tone="report"
          data-done={reported || undefined}
          onClick={() => !reported && setDialog('report')}
          aria-disabled={reported}
          aria-haspopup="dialog"
        >
          <span className="minor-action__icon" aria-hidden="true">
            {reported ? (
              <svg viewBox="0 0 24 24" width="22" height="22" focusable="false">
                <path
                  d="m5 12.5 4.5 4.5L19 7.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="22" height="22" focusable="false">
                <path
                  d="M5 21V4m0 0h11l-2 4 2 4H5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </span>
          <span className="minor-action__text">
            <span className="minor-action__label">
              {reported ? 'Zgłoszenie wysłane' : 'Zgłoś błąd'}
            </span>
            <span className="minor-action__hint">
              {reported ? 'Dziękujemy, przejrzymy wynik' : 'Coś się nie zgadza?'}
            </span>
          </span>
        </button>
        <button
          type="button"
          className="minor-action"
          data-tone="delete"
          data-done={deleted || undefined}
          onClick={() => !deleted && setDialog('delete')}
          aria-disabled={deleted}
          aria-haspopup="dialog"
        >
          <span className="minor-action__icon" aria-hidden="true">
            {deleted ? (
              <svg viewBox="0 0 24 24" width="22" height="22" focusable="false">
                <path
                  d="m5 12.5 4.5 4.5L19 7.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="22" height="22" focusable="false">
                <path
                  d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </span>
          <span className="minor-action__text">
            <span className="minor-action__label">
              {deleted ? 'Dane usunięte' : 'Usuń moje dane'}
            </span>
            <span className="minor-action__hint">
              {deleted ? 'Nie przechowujemy już wiadomości' : 'Wiadomość i ten wynik'}
            </span>
          </span>
        </button>
      </div>

      <ReportDialog
        open={dialog === 'report'}
        checkId={result.id}
        onClose={() => setDialog(null)}
        onSent={() => {
          setReported(true);
          announce('Dziękujemy za zgłoszenie.');
        }}
      />
      <DeleteDialog
        open={dialog === 'delete'}
        checkId={result.id}
        onClose={() => setDialog(null)}
        onDeleted={() => {
          setDeleted(true);
          announce('Usunęliśmy Twoją wiadomość.');
        }}
        onCheckAnother={() => {
          setDialog(null);
          speech.stop();
          goStart(true);
        }}
      />
    </div>
  );
}
