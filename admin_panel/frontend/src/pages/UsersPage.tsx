import { type FormEvent, useState } from 'react';
import { getApi, supports } from '../api/index.ts';
import type { Role, User } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { ROLE_PERMISSIONS } from '../auth/permissions.ts';
import { Icon } from '../components/icons.tsx';
import { ROLE_LABEL } from '../components/labels.ts';
import { Async, Badge, Card, Field, Modal, PageHeader, Toggle, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDate, fmtRelative } from '../utils/format.ts';

const ROLE_INFO: Record<Role, string> = {
  admin: 'Pełna kontrola nad serwisem: modele, źródła, reguły, blokady, konta i hasła.',
  analyst:
    'Panel obserwacyjny: pulpit, statystyki, alerty, luki, historia weryfikacji, logi i źródła — tylko do odczytu, z eksportem.',
  user: 'Konto bez dostępu do panelu.',
};

/** Roles an administrator can give; the first one is the default for a new account. */
const PANEL_ROLES: Role[] = ['analyst', 'admin'];

const PASSWORD_ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789';

/** Ready-to-hand-over password, e.g. `k7mp-3qat-9zhe-n4wx` (crypto-random, ~79 bits). */
function generatePassword(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const chars = Array.from(bytes, (b) => PASSWORD_ALPHABET[b % PASSWORD_ALPHABET.length]);
  return [0, 4, 8, 12].map((i) => chars.slice(i, i + 4).join('')).join('-');
}

const EMPTY_FORM = { email: '', name: '', role: PANEL_ROLES[0], password: '' };

export default function UsersPage() {
  const api = getApi();
  const { can, user: me } = useAuth();
  const users = useAsync(() => api.listUsers(), []);
  const { run, busy } = useAction();
  const [inviting, setInviting] = useState(false);
  const [form, setForm] = useState<{ email: string; name: string; role: Role; password: string }>(EMPTY_FORM);
  const [showPassword, setShowPassword] = useState(false);
  const [resetting, setResetting] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const editable = can('users:write');
  const withPasswords = supports('passwords');

  const replace = (u: User) => users.setData((list) => (list ?? []).map((x) => (x.id === u.id ? u : x)));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    let created: User | null = null;
    const ok = await run(
      async () => {
        created = await api.createUser(
          withPasswords ? form : { email: form.email, name: form.name, role: form.role },
        );
      },
      withPasswords
        ? 'Konto gotowe. Przekaż e-mail i hasło tej osobie bezpiecznym kanałem; hasło zmieni ikoną kłódki po zalogowaniu.'
        : 'Użytkownik dodany. Zaproszenie do ustawienia hasła wysyła serwer.',
    );
    if (ok && created) {
      users.setData((list) => [...(list ?? []), created as User]);
      setInviting(false);
      setForm(EMPTY_FORM);
      setShowPassword(false);
    }
  };

  const resetPassword = async () => {
    if (!resetting) return;
    const ok = await run(
      () => api.resetUserPassword(resetting.id, newPassword),
      `Nowe hasło ustawione dla ${resetting.email}. Jego dotychczasowe sesje zostały wylogowane.`,
    );
    if (ok) {
      setResetting(null);
      setNewPassword('');
    }
  };

  return (
    <>
      <PageHeader
        title="Użytkownicy i role"
        description={
          withPasswords
            ? 'Konta z dostępem do panelu i ich role. Hasła i tokeny sesji są w bazie tylko jako skróty (scrypt, SHA-256).'
            : 'Kto ma dostęp do panelu i kogo można wskazać jako odbiorcę alertów lub spraw.'
        }
        actions={
          editable && (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={() => {
                setForm({ ...EMPTY_FORM, password: withPasswords ? generatePassword() : '' });
                setShowPassword(true);
                setInviting(true);
              }}
            >
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
                      {withPasswords && editable && <th>Hasło</th>}
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
                              {(PANEL_ROLES.includes(u.role) ? PANEL_ROLES : [u.role, ...PANEL_ROLES]).map((r) => (
                                <option key={r} value={r} disabled={!PANEL_ROLES.includes(r)}>
                                  {ROLE_LABEL[r]}
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
                        {withPasswords && editable && (
                          <td>
                            <button
                              type="button"
                              className="btn btn-sm btn-ghost"
                              onClick={() => {
                                setNewPassword('');
                                setResetting(u);
                              }}
                            >
                              Ustaw hasło
                            </button>
                          </td>
                        )}
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
            {PANEL_ROLES.map((r) => (
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
              {PANEL_ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </Field>
          {withPasswords && (
            <Field
              label="Hasło początkowe"
              hint="Wygenerowane losowo — skopiuj je i przekaż tej osobie razem z adresem e-mail. Po zapisaniu nie będzie już widoczne."
            >
              <div className="row gap-xs">
                <input
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  className="mono"
                  value={form.password}
                  minLength={10}
                  required
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                />
                <button type="button" className="btn btn-sm" onClick={() => setForm({ ...form, password: generatePassword() })}>
                  Nowe
                </button>
                <button type="button" className="btn btn-sm" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? 'Ukryj' : 'Pokaż'}
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => void navigator.clipboard?.writeText(form.password)}
                  title="Kopiuj hasło do schowka"
                >
                  Kopiuj
                </button>
              </div>
            </Field>
          )}
        </form>
      </Modal>

      <Modal
        open={!!resetting}
        onClose={() => setResetting(null)}
        title="Ustaw nowe hasło"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setResetting(null)}>
              Anuluj
            </button>
            <button type="button" className="btn btn-primary" disabled={busy || newPassword.length < 10} onClick={resetPassword}>
              Ustaw hasło
            </button>
          </>
        }
      >
        <p>
          Konto: <strong>{resetting?.email}</strong>. Po zmianie wszystkie sesje tego konta zostaną wylogowane.
        </p>
        <Field label="Nowe hasło" hint="Co najmniej 10 znaków.">
          <input type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        </Field>
      </Modal>
    </>
  );
}
