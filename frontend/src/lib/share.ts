/** Parametr adresu, pod którym przekazywana jest wiadomość do sprawdzenia. */
export const QUERY_PARAM = 'q';

/** Link, który po otwarciu od razu sprawdza tę samą wiadomość. */
export function buildShareUrl(text: string): string {
  const url = new URL('/', window.location.origin);
  url.searchParams.set(QUERY_PARAM, text);
  return url.toString();
}

/** Kopiuje link do wyniku do schowka. Zwraca `false`, gdy przeglądarka na to nie pozwala. */
export async function shareLink(text: string): Promise<boolean> {
  const link = buildShareUrl(text);
  try {
    await navigator.clipboard.writeText(link);
    return true;
  } catch {
    // Starsze przeglądarki lub brak uprawnień do schowka.
    const area = document.createElement('textarea');
    area.value = link;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch {
      ok = false;
    }
    area.remove();
    return ok;
  }
}
