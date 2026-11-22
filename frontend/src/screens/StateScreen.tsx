import { useChecker, type StateKind } from '../lib/checker.ts';

interface StateContent {
  icon: string;
  tone: 'info' | 'neutral' | 'warning';
  title: string;
  body: string;
  action: string;
}

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

export default function StateScreen({ kind }: { kind: StateKind }) {
  const { goStart, retry } = useChecker();
  const content = CONTENT[kind];

  const onAction = () => {
    if (kind === 'clarify') goStart(false);
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
    </div>
  );
}
