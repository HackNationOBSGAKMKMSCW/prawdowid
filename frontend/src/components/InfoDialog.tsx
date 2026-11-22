import {
  AccessibilityContent,
  HelpContent,
  HowItWorksContent,
  SourcesContent,
} from './InfoSections.tsx';
import Modal from './Modal.tsx';

export type InfoKind = 'how' | 'sources' | 'a11y' | 'help';

const META: Record<InfoKind, { title: string; lead: string }> = {
  how: {
    title: 'Jak to działa',
    lead: 'Prawdowid porównuje Twoją wiadomość z wiarygodnymi źródłami i mówi prostym językiem, co znalazł.',
  },
  sources: {
    title: 'Lista źródeł',
    lead: 'Porównujemy wiadomości tylko ze źródłami z tej listy. Lista jest jawna, żeby każdy mógł ją sprawdzić.',
  },
  a11y: {
    title: 'Deklaracja dostępności',
    lead: 'Chcemy, żeby z Prawdowida mógł korzystać każdy, także osoby z niepełnosprawnościami i osoby starsze.',
  },
  help: { title: 'Pomoc', lead: 'Kliknij pytanie, żeby zobaczyć odpowiedź.' },
};

interface InfoDialogProps {
  kind: InfoKind | null;
  onClose: () => void;
  onSwitch: (kind: InfoKind) => void;
}

/** Okno z treścią informacyjną, otwierane przyciskami w stopce. */
export default function InfoDialog({ kind, onClose, onSwitch }: InfoDialogProps) {
  const meta = kind ? META[kind] : META.how;

  return (
    <Modal open={kind !== null} onClose={onClose} title={meta.title} wide>
      <p className="modal__text">{meta.lead}</p>
      <div className="modal__content">
        {kind === 'how' && <HowItWorksContent level={3} />}
        {kind === 'sources' && <SourcesContent level={3} />}
        {kind === 'a11y' && <AccessibilityContent level={3} />}
        {kind === 'help' && <HelpContent onShowSources={() => onSwitch('sources')} />}
      </div>
      <div className="modal__actions">
        <button type="button" className="btn-primary btn-primary--md" onClick={onClose}>
          Zamknij
        </button>
      </div>
    </Modal>
  );
}
