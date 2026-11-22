/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `mock` (domyślnie) albo `live`. */
  readonly VITE_API_MODE?: string;
  /** Adres API, domyślnie `/api`. */
  readonly VITE_API_BASE_URL?: string;
  /** `true` / `false` – pasek z przykładami. Domyślnie widoczny w trybie `mock`. */
  readonly VITE_DEMO_BAR?: string;
  /** Numer WhatsApp pokazywany na stronie startowej. */
  readonly VITE_WHATSAPP_NUMBER?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
