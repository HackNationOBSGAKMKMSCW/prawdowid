import { useState } from 'react';
import { getApi, supports } from '../api/index.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { Async, Card, EmptyState, PageHeader, SearchInput } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv } from '../utils/export.ts';
import { fmtDateTime } from '../utils/format.ts';

export default function AuditPage() {
  const api = getApi();
  const { can } = useAuth();
  const audit = useAsync(() => api.listAudit(), []);
  const [search, setSearch] = useState('');
  const rows = (audit.data ?? []).filter(
    (a) => !search.trim() || `${a.actor} ${a.action} ${a.target} ${a.detail ?? ''}`.toLowerCase().includes(search.trim().toLowerCase()),
  );

  return (
    <>
      <PageHeader
        title="Dziennik audytu"
        description={
          supports('runtimeConfig')
            ? 'Kto, kiedy i co zmienił w konfiguracji backendu: modele, źródła danych, klucze API (tylko końcówka) i progi reguł.'
            : 'Kto, kiedy i co zmienił: modele, źródła, reguły, sprawy, użytkownicy, logowania.'
        }
        actions={
          can('export') && (
            <button
              type="button"
              className="btn btn-sm"
              onClick={() =>
                exportCsv('dziennik-audytu', rows, [
                  { header: 'czas', value: (a) => a.at },
                  { header: 'kto', value: (a) => a.actor },
                  { header: 'akcja', value: (a) => a.action },
                  { header: 'obiekt', value: (a) => a.target },
                  { header: 'szczegóły', value: (a) => a.detail ?? '' },
                ])
              }
            >
              <Icon name="download" size={16} /> CSV
            </button>
          )
        }
      />
      <div className="toolbar">
        <SearchInput value={search} onChange={setSearch} placeholder="Szukaj osoby, akcji, obiektu…" />
      </div>
      <Card padded={false}>
        <Async state={audit}>
          {() =>
            rows.length === 0 ? (
              <EmptyState title="Brak wpisów" icon="audit" />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Czas</th>
                      <th>Kto</th>
                      <th>Akcja</th>
                      <th>Obiekt</th>
                      <th>Szczegóły</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((a) => (
                      <tr key={a.id}>
                        <td className="small nowrap">{fmtDateTime(a.at)}</td>
                        <td className="small">{a.actor}</td>
                        <td>{a.action}</td>
                        <td className="small">{a.target}</td>
                        <td className="small muted">{a.detail}</td>
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
