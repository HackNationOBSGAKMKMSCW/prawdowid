import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { useGoToSection } from '../lib/navigation.ts';

const ICONS: Record<string, ReactNode> = {
  how: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6M12 7.5v.01" />
    </>
  ),
  sources: (
    <>
      <path d="M9 6h11M9 12h11M9 18h11" />
      <path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01" />
    </>
  ),
  a11y: (
    <>
      <circle cx="12" cy="4.5" r="1.5" />
      <path d="M5 8.5l7 1.5 7-1.5M12 10v4.5M12 14.5l-3 6M12 14.5l3 6" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.7M12 17v.01" />
    </>
  ),
};

function Icon({ name }: { name: keyof typeof ICONS }) {
  return (
    <svg
      className="footer-link__icon"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {ICONS[name]}
    </svg>
  );
}

export default function Footer() {
  const goToSection = useGoToSection();

  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <nav aria-label="Informacje">
          <ul className="footer-links">
            <li>
              <a href="/#jak" className="footer-link" onClick={(e) => goToSection(e, 'jak')}>
                <Icon name="how" />
                Jak to działa
              </a>
            </li>
            <li>
              <a href="/#zrodla" className="footer-link" onClick={(e) => goToSection(e, 'zrodla')}>
                <Icon name="sources" />
                Lista źródeł
              </a>
            </li>
            <li>
              <NavLink to="/deklaracja-dostepnosci" className="footer-link">
                <Icon name="a11y" />
                Deklaracja dostępności
              </NavLink>
            </li>
            <li>
              <NavLink to="/pomoc" className="footer-link">
                <Icon name="help" />
                Pomoc
              </NavLink>
            </li>
          </ul>
        </nav>
        <p className="site-footer__owner">
          <span className="brand__flag brand__flag--sm" aria-hidden="true" />
          Ministerstwo Spraw Zagranicznych
        </p>
      </div>
    </footer>
  );
}
