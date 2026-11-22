import type { ReactNode } from 'react';
import type { MaskedLabel } from '../api/types.ts';

/** Nazwy typów danych osobowych z `backend/dataMasking`. */
export const MASKED_LABELS: Record<MaskedLabel, string> = {
  PESEL: 'PESEL',
  NIP: 'NIP',
  REGON: 'REGON',
  NR_KONTA: 'Numer konta',
  KARTA: 'Karta płatnicza',
  DOWOD: 'Dowód osobisty',
  PASZPORT: 'Paszport',
  TELEFON: 'Telefon',
  EMAIL: 'E-mail',
  IP: 'Adres IP',
  ADRES: 'Adres',
  KOD_POCZTOWY: 'Kod pocztowy',
  DATA_URODZENIA: 'Data urodzenia',
  NR_REJESTRACYJNY: 'Numer rejestracyjny',
  PROFIL: 'Profil / nick',
  MAC: 'Adres MAC',
  KSIEGA_WIECZYSTA: 'Księga wieczysta',
  HASLO: 'Hasło / PIN',
  LOGIN: 'Login',
  IDENTYFIKATOR: 'Numer klienta / umowy / paczki',
  LOKALIZACJA: 'Lokalizacja',
  WIEK: 'Wiek',
};

const PLACEHOLDER = /(\[[A-Z_]+_\d+\])/;

/** Wyróżnia znaczniki `[TYP_N]` w zamaskowanym tekście. */
export function highlightPlaceholders(text: string): ReactNode[] {
  return text.split(PLACEHOLDER).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="masking-tag">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}
