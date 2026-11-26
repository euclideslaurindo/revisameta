import { Component, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

const STORE = 'rm.guide.hidden';

function readHidden(): string[] {
  try {
    return JSON.parse(localStorage.getItem(STORE) ?? '[]') as string[];
  } catch {
    return [];
  }
}

/**
 * "How to do this step" (7.11): short steps and common mistakes for the current
 * project page. Open the first time; once hidden it stays hidden on this device.
 */
@Component({
  selector: 'rm-step-guide',
  imports: [TranslocoPipe],
  template: `
    @if (key(); as k) {
      @if (hidden()) {
        <button type="button" class="guide-toggle" (click)="toggle(false)">
          <span aria-hidden="true">?</span> {{ 'guide.show' | transloco }}
        </button>
      } @else {
        <aside class="step-guide" [attr.aria-label]="'guide.title' | transloco">
          <div class="step-guide-head">
            <strong>{{ 'guide.title' | transloco }}</strong>
            <button type="button" class="link" (click)="toggle(true)">
              {{ 'guide.hide' | transloco }}
            </button>
          </div>
          <ol>
            @for (item of list(k, 'do'); track $index) {
              <li>{{ item }}</li>
            }
          </ol>
          @if (list(k, 'avoid').length) {
            <p class="step-guide-avoid">
              <strong>{{ 'guide.mistakes' | transloco }}:</strong>
              @for (item of list(k, 'avoid'); track $index) {
                <span>{{ item }}</span>
              }
            </p>
          }
        </aside>
      }
    }
  `,
})
export class StepGuide {
  private readonly transloco = inject(TranslocoService);
  /** Guide key of the current page (see i18n "guide.steps"). */
  readonly key = input<string | null>(null);
  private readonly hiddenKeys = signal<string[]>(readHidden());
  protected readonly hidden = computed(() => {
    const k = this.key();
    return k !== null && this.hiddenKeys().includes(k);
  });

  protected list(key: string, part: 'do' | 'avoid'): string[] {
    const value: unknown = this.transloco.translateObject(`guide.steps.${key}.${part}`);
    return Array.isArray(value) ? (value as string[]) : [];
  }

  protected toggle(hide: boolean): void {
    const k = this.key();
    if (!k) return;
    const next = hide
      ? [...new Set([...this.hiddenKeys(), k])]
      : this.hiddenKeys().filter((x) => x !== k);
    this.hiddenKeys.set(next);
    try {
      localStorage.setItem(STORE, JSON.stringify(next));
    } catch {
      // Private mode: the choice lasts until the page reloads.
    }
  }
}

/** "Previous / Next step" links at the end of every project page. */
@Component({
  selector: 'rm-step-pager',
  imports: [TranslocoPipe, RouterLink],
  template: `
    <nav class="step-pager" [attr.aria-label]="'project.nav.label' | transloco">
      @if (previous(); as p) {
        <a class="prev" [routerLink]="p.path"
          >← {{ 'guide.previous' | transloco: { name: (p.label | transloco) } }}</a
        >
      } @else {
        <span></span>
      }
      @if (next(); as n) {
        <a class="next" [routerLink]="n.path"
          >{{ 'guide.next' | transloco: { name: (n.label | transloco) } }} →</a
        >
      }
    </nav>
  `,
})
export class StepPager {
  readonly previous = input<{ path: string; label: string } | null>(null);
  readonly next = input<{ path: string; label: string } | null>(null);
}
