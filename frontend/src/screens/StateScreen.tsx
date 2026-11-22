import type { ApiErrorCode } from '../api/client.ts';
import { type FailureInfo, useChecker, type StateKind } from '../lib/checker.ts';

interface StateContent {
  icon: string;
  tone: 'info' | 'neutral' | 'warning';
  title: string;
  body: string;
  action: string;
  /** `edit` wraca do formularza z treścią (trzeba ją poprawić), `retry` ponawia sprawdzenie. */
  then?: 'edit' | 'retry';
}

const LINK_ACTION = 'Popraw wiadomość';

/** Komunikaty dla kodów błędów backendu. Brak wpisu = ogólne „Coś poszło nie tak”. */
const FAILURES: Partial<Record<ApiErrorCode, StateContent>> = {
  invalid_url: {
    icon: '?',
    tone: 'info',
    title: 'Ten link wygląda na niepoprawny',
    body: 'Wklej sam adres publicznej strony (zaczyna się od https://) albo sam tekst wiadomości — bez łączenia ich w jednym polu.',
    action: LINK_ACTION,
    then: 'edit',
  },
  unsafe_url: {
    icon: '?',
    tone: 'info',
    title: 'Nie możemy otworzyć tego linku',
    body: 'Sprawdzamy tylko publiczne strony internetowe. Wklej treść wiadomości zamiast linku.',
    action: LINK_ACTION,
    then: 'edit',
  },
  url_unavailable: {
    icon: '?',
    tone: 'info',
    title: 'Nie możemy otworzyć tego linku',
    body: 'Strona nie odpowiada albo adres ma błąd. Sprawdź link albo wklej treść artykułu.',
    action: LINK_ACTION,
    then: 'edit',
  },
  request_too_large: {
    icon: '…',
    tone: 'info',
    title: 'Ta wiadomość jest za długa',
    body: 'Wklej najważniejszy fragment — najwyżej 20 000 znaków.',
    action: 'Skróć wiadomość',
    then: 'edit',
  },
  invalid_request: {
    icon: '?',
    tone: 'info',
    title: 'Nie możemy sprawdzić tej wiadomości',
    body: 'Sprawdź, czy wiadomość nie jest pusta i nie zawiera samych znaków specjalnych.',
    action: LINK_ACTION,
    then: 'edit',
  },
  request_refused: {
    icon: '!',
    tone: 'warning',
    title: 'Nie pomożemy w tej sprawie',
    body: 'Sprawdzamy prawdziwość informacji. Nie odpowiadamy na prośby o instrukcje dotyczące broni, materiałów wybuchowych ani przemocy.',
    action: 'Sprawdź coś innego',
    then: 'edit',
  },
  user_blocked: {
    icon: '!',
    tone: 'warning',
    title: 'Sprawdzanie jest czasowo wstrzymane',
    body: 'Z tego połączenia przychodziły powtarzające się pytania o treści niebezpieczne. Jeśli to pomyłka, skontaktuj się z administratorem serwisu.',
    action: 'Wróć na start',
    then: 'edit',
  },
  analysis_busy: {
    icon: '…',
    tone: 'neutral',
    title: 'Sprawdzamy teraz dużo wiadomości',
    body: 'Wszystkie miejsca są zajęte. Spróbuj ponownie za minutę.',
    action: 'Spróbuj jeszcze raz',
  },
  analysis_timeout: {
    icon: '…',
    tone: 'warning',
    title: 'Sprawdzanie trwało za długo',
    body: 'Źródła odpowiadały zbyt wolno. Spróbuj jeszcze raz za chwilę.',
    action: 'Spróbuj jeszcze raz',
  },
  timeout: {
    icon: '…',
    tone: 'warning',
    title: 'Sprawdzanie trwało za długo',
    body: 'Nie dostaliśmy wyniku na czas. Spróbuj jeszcze raz za chwilę.',
    action: 'Spróbuj jeszcze raz',
  },
  network: {
    icon: '!',
    tone: 'warning',
    title: 'Brak połączenia',
    body: 'Nie możemy połączyć się z serwisem Sprawdź.To. Sprawdź internet i spróbuj ponownie.',
    action: 'Spróbuj jeszcze raz',
  },
};

const CONTENT: Record<StateKind, StateContent> = {
  clarify: {
    icon: '?',
    tone: 'info',
    title: 'Napisz trochę więcej',
    body: 'Nie wiemy, co mamy sprawdzić. Napisz, co usłyszałeś albo przeczytałeś.',
    action: 'Napisz jeszcze raz',
  },
  out_of_scope: {
    icon: '↗',
    tone: 'neutral',
    title: 'Tego nie sprawdzamy',
    body: 'Sprawdzamy wiadomości o sprawach publicznych. Nie odpowiadamy na pytania o pogodę, zdrowie czy pieniądze.',
    action: 'Sprawdź coś innego',
  },
  failure: {
    icon: '!',
    tone: 'warning',
    title: 'Coś poszło nie tak',
    body: 'To błąd po naszej stronie. Spróbuj jeszcze raz za chwilę.',
    action: 'Spróbuj jeszcze raz',
  },
};

export default function StateScreen({ kind, failure }: { kind: StateKind; failure?: FailureInfo }) {
  const { goStart, retry } = useChecker();
  const content = (kind === 'failure' && failure && FAILURES[failure.code]) || CONTENT[kind];

  const onAction = () => {
    if (kind === 'clarify' || content.then === 'edit') goStart(false);
    else if (kind === 'out_of_scope') goStart(true);
    else retry();
  };

  return (
    <div className="page page--center page--state">
      <span className="state-icon" data-tone={content.tone} aria-hidden="true">
        {content.icon}
      </span>
      <h1 className="title-l" tabIndex={-1}>
        {content.title}
      </h1>
      <p className="lead">{content.body}</p>
      <button
        type="button"
        className="btn-primary btn-primary--md btn-primary--block"
        onClick={onAction}
      >
        {content.action}
      </button>
      <span className="note">To nie jest ocena Twojej wiadomości.</span>
      {kind === 'failure' && failure?.requestId && (
        <span className="note note--muted">
          Numer zdarzenia: <span className="mono-id">{failure.requestId}</span>
        </span>
      )}
    </div>
  );
}
