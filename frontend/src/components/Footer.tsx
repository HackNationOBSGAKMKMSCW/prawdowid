import { Link } from 'react-router-dom';
import { useGoToSection } from '../lib/navigation.ts';

export default function Footer() {
  const goToSection = useGoToSection();

  return (
    <footer className="site-footer">
      <nav className="site-footer__nav" aria-label="Informacje">
        <a href="/#jak" onClick={(e) => goToSection(e, 'jak')}>
          Jak to działa
        </a>
        <a href="/#zrodla" onClick={(e) => goToSection(e, 'zrodla')}>
          Lista źródeł
        </a>
        <Link to="/deklaracja-dostepnosci">Deklaracja dostępności</Link>
        <Link to="/pomoc">Pomoc</Link>
        <span className="site-footer__owner">Ministerstwo Spraw Zagranicznych</span>
      </nav>
    </footer>
  );
}
