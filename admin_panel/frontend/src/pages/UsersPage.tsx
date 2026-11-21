import { type FormEvent, useState } from 'react';
import { getApi } from '../api/index.ts';
import type { Role, User } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { ROLE_PERMISSIONS } from '../auth/permissions.ts';
import { Icon } from '../components/icons.tsx';
import { ROLE_LABEL } from '../components/labels.ts';
import { Async, Badge, Card, Field, Modal, PageHeader, Toggle, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDate, fmtRelative } from '../utils/format.ts';

const ROLE_INFO: Record<Role, string> = {
  admin: 'Konfiguracja systemu: modele, reguły, kanały, użytkownicy, prywatność.',
  analyst: 'Luki informacyjne, katalog źródeł, sprawy przekazane do analizy.',
  moderator: 'Alerty, sprawy moderatora, przekazywanie spraw.',
};

export default function UsersPage() {
  const api = getApi();
  const { can, user: me } = useAuth();
  const users = useAsync(() => api.listUsers(), []);
  const { run, busy } = useAction();
  const [inviting, setInviting] = useState(false);
  const [form, setForm] = useState<{ email: string; name: string; role: Role }>({ email: '', name: '', role: 'moderator' });
  const editable = can('users:write');

  const replace = (u: User) => users.setData((list) => (list ?? []).map((x) => (x.id === u.id ? u : x)));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    let created: User | null = null;
    const ok = await run(async () => {
      created = await api.createUser(form);
    }, 'Użytkownik dodany. Zaproszenie do ustawienia hasła wysyła serwer.');
    if (ok && created) {
      users.setData((list) => [...(list ?? []), created as User]);
      setInviting(false);
      setForm({ email: '', name: '', role: 'moderator' });
    }
  };

  return (
    <>
      <PageHeader
        title="Użytkownicy i role"
        description="Kto ma dostęp do panelu i kogo można wskazać jako odbiorcę alertów lub spraw."
        actions={
          editable && (
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setInviting(true)}>
              <Icon name="plus" size={16} /> Dodaj użytkownika
            </button>
          )
        }
      />
      <div className="grid-2-1">
        <Card padded={false}>
          <Async state={users}>
            {(list) => (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Użytkownik</th>
                      <th>Rola</th>
                      <th>Ostatnie logowanie</th>
                      <th>Aktywny</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((u) => (
                      <tr key={u.id}>
                        <td>
                          <strong>{u.name}</strong> {u.id === me?.id && <Badge tone="info">to Ty</Badge>}
                          <div className="muted small">{u.email}</div>
                          <div className="muted small">od {fmtDate(u.createdAt)}</div>
                        </td>
                        <td>
                          {editable && u.id !== me?.id ? (
                            <select
                              value={u.role}
                              disabled={busy}
                              aria-label={`Rola: ${u.name}`}
                              onChange={(e) => run(async () => replace(await api.updateUser(u.id, { role: e.target.value as Role })), 'Rola zmieniona.')}
                            >
                              {Object.entries(ROLE_LABEL).map(([k, v]) => (
                                <option key={k} value={k}>
                                  {v}
                                </option>
                              ))}
                            </select>
                          ) : (
                            ROLE_LABEL[u.role]
                          )}
                        </td>
                        <td className="small">{u.lastLoginAt ? fmtRelative(u.lastLoginAt) : <span className="muted">nigdy</span>}</td>
                        <td>
                          <Toggle
                            checked={u.active}
                            disabled={!editable || u.id === me?.id || busy}
                            label={u.active ? 'Tak' : 'Nie'}
                            onChange={(active) => run(async () => replace(await api.updateUser(u.id, { active })), active ? 'Konto aktywne.' : 'Konto dezaktywowane.')}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Async>
        </Card>
        <Card title="Role">
          <ul className="role-list">
            {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
              <li key={r}>
                <strong>{ROLE_LABEL[r]}</strong>
                <span className="muted small">{ROLE_INFO[r]}</span>
                <span className="muted small">{ROLE_PERMISSIONS[r].size} uprawnień</span>
              </li>
            ))}
          </ul>
          <p className="muted small">Uprawnienia egzekwuje serwer; panel jedynie ukrywa niedostępne akcje.</p>
        </Card>
      </div>

      <Modal
        open={inviting}
        onClose={() => setInviting(false)}
        title="Dodaj użytkownika"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setInviting(false)}>
              Anuluj
            </button>
            <button type="submit" form="user-form" className="btn btn-primary" disabled={busy}>
              Dodaj
            </button>
          </>
        }
      >
        <form id="user-form" className="form-grid" onSubmit={submit}>
          <Field label="Imię i nazwisko">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={80} />
          </Field>
          <Field label="Adres e-mail (służbowy)">
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required maxLength={120} />
          </Field>
          <Field label="Rola" hint={ROLE_INFO[form.role]}>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {Object.entries(ROLE_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
        </form>
      </Modal>
    </>
  );
}
