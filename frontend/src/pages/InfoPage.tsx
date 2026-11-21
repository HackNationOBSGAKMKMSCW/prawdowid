import { useEffect, useRef, type ReactNode } from 'react';
import { useGoHome } from '../lib/navigation.ts';
import { usePageTitle } from '../lib/usePageTitle.ts';

interface InfoPageProps {
  title: string;
  lead?: string;
  children?: ReactNode;
}

/** Wspólny układ podstron informacyjnych. */
export default function InfoPage({ title, lead, children }: InfoPageProps) {
  const goHome = useGoHome();
  const heading = useRef<HTMLHeadingElement>(null);
  usePageTitle(title);

  useEffect(() => {
    window.scrollTo(0, 0);
    heading.current?.focus();
  }, []);

  return (
    <div className="page page--result">
      <div className="page__head">
        <h1 ref={heading} className="title-l" tabIndex={-1}>
          {title}
        </h1>
        {lead && <p className="lead">{lead}</p>}
      </div>
      {children}
      <button type="button" className="btn-primary btn-primary--md" onClick={goHome}>
        Sprawdź wiadomość
      </button>
    </div>
  );
}
