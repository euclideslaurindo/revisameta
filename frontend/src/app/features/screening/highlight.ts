/** A piece of text and whether it matches an inclusion or exclusion keyword. */
export interface Segment {
  text: string;
  kind: 'include' | 'exclude' | null;
}

function plain(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

/**
 * Splits `text` into segments, marking every occurrence of the keywords (case and
 * accents ignored). When an inclusion and an exclusion keyword overlap, the longer wins.
 */
export function highlight(text: string, include: string[], exclude: string[]): Segment[] {
  if (!text) return [];
  const haystack = plain(text);
  const marks: ('include' | 'exclude' | null)[] = new Array(text.length).fill(null);
  const terms = [
    ...include.map((k) => ({ k: plain(k.trim()), kind: 'include' as const })),
    ...exclude.map((k) => ({ k: plain(k.trim()), kind: 'exclude' as const })),
  ]
    .filter((t) => t.k.length > 0)
    .sort((a, b) => a.k.length - b.k.length);
  for (const { k, kind } of terms) {
    let from = 0;
    while ((from = haystack.indexOf(k, from)) !== -1) {
      for (let i = from; i < from + k.length; i++) marks[i] = kind;
      from += k.length;
    }
  }
  const out: Segment[] = [];
  for (let i = 0; i < text.length; i++) {
    const last = out[out.length - 1];
    if (last && last.kind === marks[i]) last.text += text[i];
    else out.push({ text: text[i], kind: marks[i] });
  }
  return out;
}
