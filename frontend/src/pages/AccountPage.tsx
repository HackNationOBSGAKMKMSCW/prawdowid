import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { ACCOUNTS_ENABLED, ApiError, listMyChecks, type AccountCheck } from '../api/client.ts';
import { firstName, useAccount } from '../lib/account.ts';
import { useGoHome } from '../lib/navigation.ts';
import { plural } from '../lib/format.ts';
import { usePageTitle } from '../lib/usePageTitle.ts';

/** Wymagania backendu (`accounts/passwords.py`): 10–256 znaków, co najmniej 4 różne. */
const PASSWORD_HINT =
  'Co najmniej 10 znaków. Może to być kilka słów, np. „zielony rower nad Wisłą”.';

type Mode = 'signin' | 'signup';

export default function AccountPage() {
  const account = useAccount();
  const heading = useRef<HTMLHeadingElement>(null);
  const [mode, setMode] = useState<Mode>('signin');
  const signedIn = account.status === 'signed_in' && account.user;
  const title = signedIn ? 'Moje konto' : mode === 'signin' ? 'Zaloguj się' : 'Załóż konto';
  usePageTitle(title);

  useEffect(() => {
    window.scrollTo(0, 0);
    heading.current?.focus();
  }, [signedIn, mode]);

  if (!ACCOUNTS_ENABLED) {
    return (
      <Page
        title="Konto"
        headingRef={heading}
        lead="Konta działają tylko z prawdziwym serwerem Prawdowida."
      >
        <p className="note">
          Ta wersja strony pokazuje przykładowe wyniki. Sprawdzanie wiadomości nie wymaga konta.
        </p>
      </Page>
    );
  }

  if (account.status === 'loading') {
    return <Page title="Moje konto" headingRef={heading} lead="Wczytujemy Twoje konto…" />;
  }

  if (signedIn && account.user) {
    return (
      <Page
        title="Moje konto"
        headingRef={heading}
        lead={`Witaj, ${firstName(account.user)}. Sprawdzenia, które robisz po zalogowaniu, zapisują się w historii poniżej.`}
      >
        <p className="note note--muted">
          Zalogowano jako <strong>{account.user.email}</strong>.
        </p>
        <History />
        <PasswordForm />
        <button type="button" className="btn-secondary" onClick={() => void account.signOut()}>
          Wyloguj się
        </button>
      </Page>
    );
  }

  return (
    <Page
      title={title}
      headingRef={heading}
      lead={
        mode === 'signin'
          ? 'Po zalogowaniu Twoje sprawdzenia zapisują się w historii. Sprawdzanie działa też bez konta.'
          : 'Konto jest bezpłatne. Zapisuje historię Twoich sprawdzeń, żeby można było do nich wrócić.'
      }
    >
      {mode === 'signin' ? <SignInForm /> : <SignUpForm />}
      <p className="note note--center">
        {mode === 'signin' ? 'Nie masz konta? ' : 'Masz już konto? '}
        <button
          type="button"
          className="btn-link btn-link--strong"
          onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}
        >
          {mode === 'signin' ? 'Załóż konto' : 'Zaloguj się'}
        </button>
      </p>
    </Page>
  );
}

function Page({
  title,
  lead,
  headingRef,
  children,
}: {
  title: string;
  lead?: string;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  children?: ReactNode;
}) {
  return (
    <div className="page page--result">
      <div className="page__head">
        <h1 ref={headingRef} className="title-l" tabIndex={-1}>
          {title}
        </h1>
        {lead && <p className="lead">{lead}</p>}
      </div>
      {children}
    </div>
  );
}

function failureText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === 'network')
      return 'Brak połączenia z serwerem. Sprawdź internet i spróbuj ponownie.';
    if (err.code === 'timeout') return 'Serwer nie odpowiedział na czas. Spróbuj ponownie.';
    if (err.status === 404) return 'Zakładanie kont jest teraz wyłączone.';
    if (err.status >= 500) return 'To błąd po naszej stronie. Spróbuj ponownie za chwilę.';
    return err.message;
  }
  return 'Coś poszło nie tak. Spróbuj ponownie.';
}

function useForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const submit = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(failureText(err));
      window.setTimeout(() => errorRef.current?.focus(), 0);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, errorRef, submit };
}

function FormError({
  text,
  innerRef,
}: {
  text: string | null;
  innerRef: React.RefObject<HTMLParagraphElement | null>;
}) {
  if (!text) return null;
  return (
    <p ref={innerRef} className="field-error field-error--flat" role="alert" tabIndex={-1}>
      {text}
    </p>
  );
}

function Input({
  label,
  hint,
  ...props
}: { label: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="account-field">
      <label className="account-field__label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="input"
        aria-describedby={hint ? `${id}-hint` : undefined}
        {...props}
      />
      {hint && (
        <p id={`${id}-hint`} className="account-field__hint">
          {hint}
        </p>
      )}
    </div>
  );
}

function SignInForm() {
  const account = useAccount();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const form = useForm();
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void form.submit(() => account.signIn(email, password));
  };
  return (
    <form className="account-form" onSubmit={onSubmit} noValidate={false}>
      <Input
        label="Adres e-mail"
        type="email"
        autoComplete="email"
        required
        maxLength={255}
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <Input
        label="Hasło"
        type="password"
        autoComplete="current-password"
        required
        maxLength={256}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <FormError text={form.error} innerRef={form.errorRef} />
      <button type="submit" className="btn-primary btn-primary--block" disabled={form.busy}>
        {form.busy ? 'Logowanie…' : 'Zaloguj się'}
      </button>
    </form>
  );
}

function SignUpForm() {
  const account = useAccount();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const form = useForm();
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void form.submit(async () => {
      if (password !== repeat) throw new Error('Hasła się różnią. Wpisz to samo hasło dwa razy.');
      await account.signUp(name, email, password);
    });
  };
  return (
    <form className="account-form" onSubmit={onSubmit}>
      <Input
        label="Imię"
        autoComplete="given-name"
        required
        maxLength={100}
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <Input
        label="Adres e-mail"
        type="email"
        autoComplete="email"
        required
        maxLength={255}
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <Input
        label="Hasło"
        type="password"
        autoComplete="new-password"
        required
        minLength={10}
        maxLength={256}
        hint={PASSWORD_HINT}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Input
        label="Powtórz hasło"
        type="password"
        autoComplete="new-password"
        required
        minLength={10}
        maxLength={256}
        value={repeat}
        onChange={(e) => setRepeat(e.target.value)}
      />
      <FormError text={form.error} innerRef={form.errorRef} />
      <button type="submit" className="btn-primary btn-primary--block" disabled={form.busy}>
        {form.busy ? 'Zakładanie konta…' : 'Załóż konto'}
      </button>
      <p className="account-field__hint">
        Zapisujemy imię, adres e-mail i historię Twoich sprawdzeń. Hasło jest przechowywane tylko w
        postaci zaszyfrowanego skrótu.
      </p>
    </form>
  );
}

function PasswordForm() {
  const account = useAccount();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const form = useForm();
  if (!open) {
    return (
      <button type="button" className="btn-link" onClick={() => setOpen(true)}>
        Zmień hasło
      </button>
    );
  }
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void form.submit(() => account.changePassword(current, next));
  };
  return (
    <form className="account-form" onSubmit={onSubmit}>
      <h2 className="title-s">Zmiana hasła</h2>
      <Input
        label="Obecne hasło"
        type="password"
        autoComplete="current-password"
        required
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
      />
      <Input
        label="Nowe hasło"
        type="password"
        autoComplete="new-password"
        required
        minLength={10}
        maxLength={256}
        hint={`${PASSWORD_HINT} Po zmianie zalogujesz się ponownie.`}
        value={next}
        onChange={(e) => setNext(e.target.value)}
      />
      <FormError text={form.error} innerRef={form.errorRef} />
      <div className="account-form__actions">
        <button type="submit" className="btn-primary btn-primary--md" disabled={form.busy}>
          Zmień hasło
        </button>
        <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>
          Anuluj
        </button>
      </div>
    </form>
  );
}

const VERDICT: Record<string, string> = {
  prawda: 'Prawda',
  prawdziwy: 'Prawda',
  falsz: 'Fałsz',
  falszywy: 'Fałsz',
  zawiera_falsz: 'Zawiera fałsz',
  czesciowo_potwierdzony: 'Częściowo prawda',
  sprzeczne_zrodla: 'Źródła się różnią',
  brak_wystarczajacych_danych: 'Za mało danych',
  nieweryfikowalny: 'Nie da się sprawdzić',
};

function outcome(check: AccountCheck): string {
  if (check.status === 'odrzucone') return 'Nie sprawdzono';
  if (check.status === 'blad') return 'Nie udało się sprawdzić';
  if (check.status === 'w_toku') return 'Sprawdzanie przerwane';
  return (check.verdict && VERDICT[check.verdict]) || 'Sprawdzone';
}

const dateTime = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'long', timeStyle: 'short' });

function History() {
  const goHome = useGoHome();
  const [state, setState] = useState<
    { items: AccountCheck[]; total: number } | 'loading' | 'error'
  >('loading');

  useEffect(() => {
    const controller = new AbortController();
    listMyChecks(50, 0, controller.signal)
      .then(setState)
      .catch((err: unknown) => {
        if ((err as Error).name !== 'AbortError') setState('error');
      });
    return () => controller.abort();
  }, []);

  return (
    <section className="account-history" aria-labelledby="historia">
      <h2 id="historia" className="title-s">
        Moje sprawdzenia
      </h2>
      {state === 'loading' && <p className="note note--muted">Wczytujemy historię…</p>}
      {state === 'error' && (
        <p className="note">Nie udało się wczytać historii. Spróbuj odświeżyć stronę.</p>
      )}
      {typeof state === 'object' && state.items.length === 0 && (
        <p className="note">
          Nie masz jeszcze zapisanych sprawdzeń.{' '}
          <button type="button" className="btn-link btn-link--strong" onClick={goHome}>
            Sprawdź wiadomość
          </button>
        </p>
      )}
      {typeof state === 'object' && state.items.length > 0 && (
        <>
          <p className="note note--muted">
            {state.total} {plural(state.total, 'sprawdzenie', 'sprawdzenia', 'sprawdzeń')}
            {state.total > state.items.length && `, pokazujemy ${state.items.length} najnowszych`}.
          </p>
          <ul className="account-history__list">
            {state.items.map((check) => (
              <li key={check.id} className="account-history__item">
                <span className="account-history__text">{check.text || '(bez treści)'}</span>
                <span className="account-history__meta">
                  <strong>{outcome(check)}</strong> · {dateTime.format(new Date(check.ts))}
                  {check.channel === 'whatsapp' && ' · WhatsApp'}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
