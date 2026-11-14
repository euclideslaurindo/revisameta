import { AnnotationOut } from '../../core/api/models/annotation-out';

const MARK = 'rm-highlight';

/**
 * Paints saved passages on a rendered PDF page. Rectangles are stored as fractions
 * of the page, so the highlights follow any zoom. They ignore the mouse, so text
 * can still be selected under them.
 */
export function paintPage(
  root: ParentNode,
  pageNumber: number,
  annotations: AnnotationOut[],
  activeId: string | null = null,
): void {
  const page = root.querySelector<HTMLElement>(`.page[data-page-number="${pageNumber}"]`);
  if (!page) return;
  page.querySelectorAll(`.${MARK}`).forEach((el) => el.remove());
  for (const annotation of annotations) {
    if (annotation.page !== pageNumber) continue;
    for (const rect of annotation.rects) {
      const box = document.createElement('div');
      box.className = `${MARK} ${MARK}-${annotation.color}`;
      if (annotation.id === activeId) box.classList.add(`${MARK}-active`);
      box.dataset['annotationId'] = annotation.id;
      box.title = annotation.note || annotation.quote;
      box.style.left = `${rect.x * 100}%`;
      box.style.top = `${rect.y * 100}%`;
      box.style.width = `${rect.w * 100}%`;
      box.style.height = `${rect.h * 100}%`;
      page.appendChild(box);
    }
  }
}

/** Repaints every page that is currently rendered (after a passage is added or removed). */
export function paintAll(
  root: ParentNode,
  annotations: AnnotationOut[],
  activeId: string | null = null,
): void {
  root.querySelectorAll<HTMLElement>('.page[data-page-number]').forEach((page) => {
    paintPage(root, Number(page.dataset['pageNumber']), annotations, activeId);
  });
}
