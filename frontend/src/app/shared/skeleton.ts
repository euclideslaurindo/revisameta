import { Component, input } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

/** Grey placeholder blocks while a page loads (instead of a bare "Loading..."). */
@Component({
  selector: 'rm-skeleton',
  imports: [TranslocoPipe],
  template: `
    <div class="skeleton" role="status" aria-live="polite">
      <span class="sr-only">{{ 'common.loading' | transloco }}</span>
      @for (line of lines(); track $index) {
        <div class="skeleton-block" [style.height.px]="line"></div>
      }
    </div>
  `,
})
export class Skeleton {
  /** Height (px) of each placeholder block. */
  readonly lines = input<number[]>([28, 90, 90]);
}
