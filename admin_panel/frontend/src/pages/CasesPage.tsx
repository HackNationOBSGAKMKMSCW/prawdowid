import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import type { CaseQuery, ModeratorCase } from '../api/types.ts';
import { CASE_STATUS, ROLE_LABEL, SEVERITY } from '../components/labels.ts';
import { Async, Badge, Card, EmptyState, PageHeader, SearchInput, Tabs } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtRelative } from '../utils/format.ts';

export function ForwardingBadge({ c }: { c: ModeratorCase }) {
  if (c.forwarding.forwardedTo) {
    return (
      <Badge tone="good" title={`Przekazano ${c.forwarding.forwardedAt ?? ''}`}>
        Przekazano: {c.forwarding.forwardedTo.name}
      </Badge>
    );
  }
  if (c.forwarding.recommended) {
    return (
      <Badge tone="warning" title="System rekomenduje przekazanie — nic nie zostało wysłane">
        Rekomendacja → {ROLE_LABEL[c.forwarding.recommendedRole ?? 'analyst'].toLowerCase()}
      </Badge>
    );
  }
  return <span className="muted">—</span>;
}

export default function CasesPage() {
  const api = getApi();
  const navigate = useNavigate();
  const [status, setStatus] = useState<NonNullable<CaseQuery['status']>>('open');
  const [search, setSearch] = useState('');
  const cases = useAsync(() => api.listCases({ status }), [status]);
  const rows = (cases.data ?? []).filter(
    (c) => !search.trim() || `${c.id} ${c.title}`.toLowerCase().includes(search.trim().toLowerCase()),
  );

  return (
    <>
      <PageHeader
        title="Sprawy"
        description="Zamknięta pętla informacji: nierozstrzygnięte zgłoszenia trafiają do jednej sprawy na grupę podobnych zapytań. System odróżnia rekomendację przekazania od faktycznego przekazania sprawy."
      />
      <div className="toolbar">
        <Tabs
          label="Status spraw"
          value={status}
          onChange={setStatus}
          options={[
            { value: 'open', label: 'Otwarte' },
            { value: 'resolved', label: 'Rozwiązane' },
            { value: 'rejected', label: 'Odrzucone' },
            { value: 'any', label: 'Wszystkie' },
          ]}
        />
        <SearchInput value={search} onChange={setSearch} placeholder="Szukaj po numerze lub tytule…" />
      </div>
      <Card padded={false}>
        <Async state={cases}>
          {() =>
            rows.length === 0 ? (
              <EmptyState title="Brak spraw" icon="folder">
                Sprawy tworzy się z alertów lub luk informacyjnych.
              </EmptyState>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Sprawa</th>
                      <th>Priorytet</th>
                      <th>Status</th>
                      <th className="num">Zapytania</th>
                      <th>Prowadzi</th>
                      <th>Przekazanie</th>
                      <th>Aktualizacja</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((c) => (
                      <tr key={c.id} className="clickable" onClick={() => navigate(`/cases/${c.id}`)}>
                        <td>
                          <Link to={`/cases/${c.id}`} onClick={(e) => e.stopPropagation()} className="mono small">
                            {c.id}
                          </Link>
                          <div>{c.title}</div>
                          {c.riskTopics.length > 0 && (
                            <div className="row gap-xs wrap">
                              {c.riskTopics.map((r) => (
                                <Badge key={r} tone="critical">
                                  {r}
                                </Badge>
                              ))}
                            </div>
                          )}
                        </td>
                        <td>
                          <Badge tone={SEVERITY[c.priority].tone}>{SEVERITY[c.priority].label}</Badge>
                        </td>
                        <td>
                          <Badge tone={CASE_STATUS[c.status].tone}>{CASE_STATUS[c.status].label}</Badge>
                        </td>
                        <td className="num">{c.queryCount}</td>
                        <td className="small">{c.assignee?.name ?? <span className="muted">nieprzypisana</span>}</td>
                        <td>
                          <ForwardingBadge c={c} />
                        </td>
                        <td className="small nowrap">{fmtRelative(c.updatedAt)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Async>
      </Card>
    </>
  );
}
