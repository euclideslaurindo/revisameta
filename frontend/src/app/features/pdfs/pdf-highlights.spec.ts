import { describe, expect, it } from 'vitest';

import { AnnotationOut } from '../../core/api/models/annotation-out';
import { paintAll, paintPage } from './pdf-highlights';

function annotation(over: Partial<AnnotationOut>): AnnotationOut {
  return {
    id: 'a1',
    color: 'yellow',
    created_at: '',
    note: null,
    page: 1,
    pdf_file_id: 'p',
    quote: 'DP = 11,2',
    rects: [{ x: 0.1, y: 0.25, w: 0.3, h: 0.02 }],
    user_id: 'u',
    version: 1,
    ...over,
  };
}

function viewer(pages: number): HTMLElement {
  const root = document.createElement('div');
  for (let i = 1; i <= pages; i++) {
    const page = document.createElement('div');
    page.className = 'page';
    page.dataset['pageNumber'] = String(i);
    root.appendChild(page);
  }
  return root;
}

describe('PDF highlights', () => {
  it('draws each saved passage on its own page, as a fraction of the page', () => {
    const root = viewer(2);
    paintPage(root, 1, [annotation({}), annotation({ id: 'a2', page: 2 })], 'a1');
    const boxes = root.querySelectorAll<HTMLElement>('.page[data-page-number="1"] .rm-highlight');
    expect(boxes.length).toBe(1);
    expect(boxes[0].style.left).toBe('10%');
    expect(boxes[0].style.top).toBe('25%');
    expect(boxes[0].classList.contains('rm-highlight-active')).toBe(true);
    expect(boxes[0].title).toBe('DP = 11,2');
  });

  it('repainting replaces old highlights (a removed passage disappears)', () => {
    const root = viewer(2);
    paintAll(root, [annotation({}), annotation({ id: 'a2', page: 2 })]);
    expect(root.querySelectorAll('.rm-highlight').length).toBe(2);
    paintAll(root, [annotation({ id: 'a2', page: 2 })]);
    expect(root.querySelectorAll('.rm-highlight').length).toBe(1);
  });
});
