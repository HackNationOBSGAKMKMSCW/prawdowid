import { type FormEvent, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import type { CaseEventKind, CaseStatus, ModeratorCase, Severity, User } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon, type IconName } from '../components/icons.tsx';
import { CASE_STATUS, ROLE_LABEL, SEVERITY } from '../components/labels.ts';
import { useRefreshCounts } from '../components/Layout.tsx';
import { Async, Badge, Card, Field, Modal, PageHeader, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportJson } from '../utils/export.ts';
import { fmtDateTime } from '../utils/format.ts';

const EVENT_ICON: Record<CaseEventKind, IconName> = {
  created: 'plus',
  status_changed: 'refresh',
  comment: 'channels',
  queries_linked: 'repeat',
  assigned: 'users',
  forward_recommended: 'info',
  forwarded: 'send',
};

export default function CaseDetailPage() {
  const { id = '' } = useParams();
  const api = getApi();
  const { can } = useAuth();
  const refreshCounts = useRefreshCounts();
  const state = useAsync(() => api.getCase(id), [id]);
  const users = useAsync<User[]>(() => api.listUsers(), []);
  const { run, busy } = useAction();
  const [comment, setComment] = useState('');
  const [closing, setClosing] = useState<CaseStatus | null>(null);
  const [resolution, setResolution] = useState('');
  const [forwardOpen, setForwardOpen] = useState(false);
  const [forwardTo, setForwardTo] = useState('');
  const [forwardNote, setForwardNote] = useState('');

  const apply = async (action: () => Promise<ModeratorCase>, message: string) => {
    let updated: ModeratorCase | null = null;
    const ok = await run(async () => {
      updated = await action();
    }, message);
    if (ok && updated) {
      state.setData(updated);
      refreshCounts();
    }
    return ok;
  };

  const activeUsers = (users.data ?? []).filter((u) => u.active);
  const editable = can('cases:write');

  return (
    <Async state={state}>
      {(c) => {
        const closed = c.status === 'resolved' || c.status === 'rejected';
        const recommendedUsers = activeUsers.filter((u) => u.role === c.forwarding.recommendedRole);
        return (
          <>
            <div className="crumbs">
              <Link to="/cases">Sprawy moderatora</Link> / <span className="mono">{c.id}</span>
            </div>
            <PageHeader
              title={c.title}
              description={
                <span className="row gap-sm wrap">
                  <Badge tone={CASE_STATUS[c.status].tone}>{CASE_STATUS[c.status].label}</Badge>
                  <Badge tone={SEVERITY[c.priority].tone}>Priorytet: {SEVERITY[c.priority].label}</Badge>
                  {c.riskTopics.map((r) => (
                    <Badge key={r} tone="critical">
                      {r}
                    </Badge>
                  ))}
                  <span className="muted small">
                    utworzona {fmtDateTime(c.createdAt)} · aktualizacja {fmtDateTime(c.updatedAt)}
                  </span>
                </span>
              }
              actions={
                <button type="button" className="btn btn-sm" onClick={() => exportJson(`sprawa-${c.id}`, c)}>
                  <Icon name="download" size={16} /> JSON
                </button>
              }
            />

            <div className="grid-2-1">
              <div className="stack">
                <Card title="Przekazanie sprawy" subtitle="Rekomendacja systemu i faktyczne przekazanie są zapisywane osobno.">
                  <div className="forward-grid">
                    <div className={`forward-box ${c.forwarding.recommended ? 'is-on' : ''}`}>
                      <div className="forward-label">
                        <Icon name="info" size={16} /> Rekomendacja systemu
                      </div>
                      {c.forwarding.recommended ? (
                        <>
                          <p>
                            Przekazać do roli: <strong>{ROLE_LABEL[c.forwarding.recommendedRole ?? 'analyst']}</strong>
                          </p>
                          {c.forwarding.reason && <p className="muted small">Powód: {c.forwarding.reason}</p>}
                          <p className="small">
                            <em>To tylko rekomendacja — sama w sobie nic nie wysyła.</em>
                          </p>
                        </>
                      ) : (
                        <p className="muted">Brak rekomendacji.</p>
                      )}
                    </div>
                    <div className={`forward-box ${c.forwarding.forwardedTo ? 'is-done' : ''}`}>
                      <div className="forward-label">
                        <Icon name="send" size={16} /> Faktyczne przekazanie
                      </div>
                      {c.forwarding.forwardedTo ? (
                        <>
                          <p>
                            Przekazano: <strong>{c.forwarding.forwardedTo.name}</strong> ({ROLE_LABEL[c.forwarding.forwardedTo.role].toLowerCase()})
                          </p>
                          <p className="muted small">
                            {fmtDateTime(c.forwarding.forwardedAt)} · przez {c.forwarding.forwardedBy}
                          </p>
                        </>
                      ) : (
                        <p className="muted">Sprawa nie została jeszcze przekazana.</p>
                      )}
                      {can('cases:forward') && !closed && (
                        <button
                          type="button"
                          className="btn btn-sm btn-primary"
                          onClick={() => {
                            setForwardTo(recommendedUsers[0]?.id ?? '');
                            setForwardNote('');
                            setForwardOpen(true);
                          }}
                        >
                          <Icon name="send" size={14} /> {c.forwarding.forwardedTo ? 'Przekaż innej osobie' : 'Przekaż teraz'}
                        </button>
                      )}
                    </div>
                  </div>
                </Card>

                <Card title="Przebieg sprawy">
                  <ol className="timeline">
                    {c.events.map((e) => (
                      <li key={e.id} className={`tl-${e.kind}`}>
                        <span className="tl-icon">
                          <Icon name={EVENT_ICON[e.kind]} size={14} />
                        </span>
                        <div>
                          <div className="tl-text">{e.text}</div>
                          <div className="muted small">
                            {e.actor} · {fmtDateTime(e.at)}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ol>
                  {editable && (
                    <form
                      className="comment-form"
                      onSubmit={async (ev: FormEvent) => {
                        ev.preventDefault();
                        if (!comment.trim()) return;
                        if (await apply(() => api.addCaseComment(c.id, comment), 'Dodano komentarz.')) setComment('');
                      }}
                    >
                      <textarea
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        placeholder="Dodaj notatkę (bez danych osobowych)…"
                        rows={3}
                        maxLength={2000}
                        aria-label="Komentarz"
                      />
                      <button type="submit" className="btn btn-sm" disabled={busy || !comment.trim()}>
                        Dodaj komentarz
                      </button>
                    </form>
                  )}
                </Card>
              </div>

              <div className="stack">
                <Card title="Szczegóły">
                  <div className="form-grid">
                    <Field label="Status">
                      <select
                        value={c.status}
                        disabled={!editable || busy}
                        onChange={(e) => {
                          const next = e.target.value as CaseStatus;
                          if (next === 'resolved' || next === 'rejected') {
                            setResolution(c.resolution ?? '');
                            setClosing(next);
                          } else {
                            void apply(() => api.updateCase(c.id, { status: next }), 'Zmieniono status.');
                          }
                        }}
                      >
                        {Object.entries(CASE_STATUS).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v.label}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Priorytet">
                      <select
                        value={c.priority}
                        disabled={!editable || busy}
                        onChange={(e) => void apply(() => api.updateCase(c.id, { priority: e.target.value as Severity }), 'Zmieniono priorytet.')}
                      >
                        {Object.entries(SEVERITY).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v.label}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Osoba prowadząca">
                      <select
                        value={c.assignee?.id ?? ''}
                        disabled={!editable || busy}
                        onChange={(e) => void apply(() => api.updateCase(c.id, { assigneeId: e.target.value || null }), 'Zmieniono osobę prowadzącą.')}
                      >
                        <option value="">— nieprzypisana —</option>
                        {c.assignee && !activeUsers.some((u) => u.id === c.assignee?.id) && (
                          <option value={c.assignee.id}>{c.assignee.name}</option>
                        )}
                        {activeUsers.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.name} ({ROLE_LABEL[u.role].toLowerCase()})
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                  <dl className="metrics">
                    <div>
                      <dt>Powiązane zapytania</dt>
                      <dd>{c.queryCount}</dd>
                    </div>
                    <div>
                      <dt>Alerty</dt>
                      <dd>{c.alertIds.length}</dd>
                    </div>
                  </dl>
                  {c.clusterId && (
                    <Link to={`/checks?cluster=${encodeURIComponent(c.clusterId)}`} className="btn btn-sm btn-block">
                      <Icon name="history" size={14} /> Zobacz zapytania tej grupy
                    </Link>
                  )}
                  {c.resolution && (
                    <div className="notice notice-good">
                      <Icon name="check" size={16} />
                      <div>
                        <strong>Rozstrzygnięcie:</strong> {c.resolution}
                      </div>
                    </div>
                  )}
                </Card>
                <Card title="Zasady">
                  <ul className="bullets small">
                    <li>Jedna sprawa na grupę podobnych zapytań — kolejne zgłoszenia aktualizują tę sprawę.</li>
                    <li>Odpowiedzi wymagające publikacji zatwierdza człowiek.</li>
                    <li>Zamknięcie sprawy wymaga opisu rozstrzygnięcia (np. dodane źródło, opublikowany komunikat).</li>
                  </ul>
                </Card>
              </div>
            </div>

            <Modal
              open={closing !== null}
              onClose={() => setClosing(null)}
              title={closing === 'resolved' ? 'Rozwiąż sprawę' : 'Odrzuć sprawę'}
              footer={
                <>
                  <button type="button" className="btn" onClick={() => setClosing(null)}>
                    Anuluj
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy || !resolution.trim()}
                    onClick={async () => {
                      if (closing && (await apply(() => api.updateCase(c.id, { status: closing, resolution }), 'Sprawa zamknięta.'))) setClosing(null);
                    }}
                  >
                    Zapisz
                  </button>
                </>
              }
            >
              <Field label="Rozstrzygnięcie" hint="Co zrobiono? Np. „Dodano komunikat sanepidu do katalogu źródeł”.">
                <textarea rows={4} value={resolution} onChange={(e) => setResolution(e.target.value)} maxLength={2000} />
              </Field>
            </Modal>

            <Modal
              open={forwardOpen}
              onClose={() => setForwardOpen(false)}
              title="Przekaż sprawę"
              footer={
                <>
                  <button type="button" className="btn" onClick={() => setForwardOpen(false)}>
                    Anuluj
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy || !forwardTo}
                    onClick={async () => {
                      if (await apply(() => api.forwardCase(c.id, forwardTo, forwardNote), 'Sprawa przekazana — odbiorca dostał powiadomienie.')) {
                        setForwardOpen(false);
                      }
                    }}
                  >
                    Przekaż
                  </button>
                </>
              }
            >
              <p className="small">
                Przekazanie wysyła powiadomienie do wybranej osoby i jest zapisywane w przebiegu sprawy oraz dzienniku
                audytu.
              </p>
              <Field label="Odbiorca">
                <select value={forwardTo} onChange={(e) => setForwardTo(e.target.value)}>
                  <option value="">— wybierz —</option>
                  {activeUsers.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} ({ROLE_LABEL[u.role].toLowerCase()})
                      {u.role === c.forwarding.recommendedRole ? ' — zgodnie z rekomendacją' : ''}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Notatka (opcjonalnie)">
                <textarea rows={3} value={forwardNote} onChange={(e) => setForwardNote(e.target.value)} maxLength={500} />
              </Field>
            </Modal>
          </>
        );
      }}
    </Async>
  );
}
