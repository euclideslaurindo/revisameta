import { Component, inject, input, output, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';
import { toSignal } from '@angular/core/rxjs-interop';

import { Api } from '../../core/api/api';
import { confirmDirection } from '../../core/api/fn/extraction/confirm-direction';
import { DirectionOut } from '../../core/api/models/direction-out';
import { FormError } from '../../shared/form-error';
import { displayDecimal } from '../../shared/numbers';

/**
 * Block C: a plain sentence built from the typed numbers, so the extractor can see
 * at a glance whether the data point the way the article says.
 */
@Component({
  selector: 'rm-direction-check',
  imports: [TranslocoPipe, MatButtonModule, FormError],
  template: `
    @for (d of summaries(); track d.outcome_id + d.timepoint) {
      <div class="direction" [class.confirmed]="d.confirmed">
        <p>
          {{
            'extraction.direction.sentence'
              | transloco
                : {
                    study: studyLabel(),
                    outcome: d.outcome_name,
                    timepoint: d.timepoint,
                    first: d.first.arm_label,
                    meanFirst: num(d.first.mean),
                    second: d.second.arm_label,
                    meanSecond: num(d.second.mean),
                    scale: d.scale_name || d.outcome_name,
                  }
          }}
          {{
            (d.higher_is_better
              ? 'extraction.direction.higherBetter'
              : 'extraction.direction.higherWorse'
            ) | transloco
          }}
          <strong>
            @switch (d.favors) {
              @case ('first') {
                {{ 'extraction.direction.favors' | transloco: { group: d.first.group_label } }}
              }
              @case ('second') {
                {{ 'extraction.direction.favors' | transloco: { group: d.second.group_label } }}
              }
              @default {
                {{ 'extraction.direction.equal' | transloco }}
              }
            }
          </strong>
        </p>
        @if (d.confirmed) {
          <span class="badge">{{ 'extraction.direction.confirmed' | transloco }}</span>
        } @else if (editable()) {
          <div class="actions">
            <span class="muted">{{ 'extraction.direction.ifWrong' | transloco }}</span>
            <button mat-flat-button type="button" [disabled]="busy()" (click)="confirm(d)">
              {{ 'extraction.direction.confirm' | transloco }}
            </button>
          </div>
        }
      </div>
    }
    @if (summaries().length === 0) {
      <p class="muted">{{ 'extraction.direction.none' | transloco }}</p>
    }
    <rm-form-error [error]="error()" />
  `,
})
export class DirectionCheck {
  private readonly api = inject(Api);
  private readonly lang = toSignal(inject(TranslocoService).langChanges$, {
    initialValue: 'pt-BR',
  });

  readonly projectId = input.required<string>();
  readonly extractionId = input.required<string>();
  readonly studyLabel = input('');
  readonly summaries = input<DirectionOut[]>([]);
  readonly editable = input(false);
  readonly changed = output<DirectionOut[]>();

  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  protected num(value: string): string {
    return displayDecimal(value, this.lang());
  }

  async confirm(summary: DirectionOut): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.changed.emit(
        await this.api.invoke(confirmDirection, {
          project_id: this.projectId(),
          extraction_id: this.extractionId(),
          body: { outcome_id: summary.outcome_id, timepoint: summary.timepoint },
        }),
      );
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
