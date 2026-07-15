/** One date language for the whole app: "12 Jan 2026" / "12 Jan 2026, 14:03". */

const DATE = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(iso: string): string {
  return DATE.format(new Date(iso));
}

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

/** "p. 12" or "pp. 12–14" — the citation page reference used everywhere. */
export function formatPages(start: number, end: number): string {
  return start === end ? `p. ${start}` : `pp. ${start}–${end}`;
}
