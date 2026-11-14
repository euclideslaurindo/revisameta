import { Rect } from '../../core/api/models/rect';

export interface PdfSelection {
  page: number;
  quote: string;
  rects: Rect[];
}

/** Reads the current text selection inside the PDF viewer as page-relative rectangles. */
export function readPdfSelection(): PdfSelection | null {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const quote = selection.toString().replace(/\s+/g, ' ').trim();
  if (!quote) return null;
  const range = selection.getRangeAt(0);
  const start =
    range.startContainer instanceof Element
      ? range.startContainer
      : range.startContainer.parentElement;
  const pageEl = start?.closest<HTMLElement>('.page[data-page-number]');
  if (!pageEl) return null;
  const box = pageEl.getBoundingClientRect();
  const rects = Array.from(range.getClientRects())
    .filter((r) => r.width > 1 && r.height > 1)
    .map((r) => ({
      x: Math.max(0, (r.left - box.left) / box.width),
      y: Math.max(0, (r.top - box.top) / box.height),
      w: Math.min(1, r.width / box.width),
      h: Math.min(1, r.height / box.height),
    }));
  return { page: Number(pageEl.dataset['pageNumber']), quote, rects };
}
