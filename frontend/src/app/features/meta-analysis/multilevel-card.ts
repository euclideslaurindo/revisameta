import { Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { runMultilevel } from '../../core/api/fn/analysis/run-multilevel';
import { MultilevelOut } from '../../core/api/models/multilevel-out';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { formatNumber, formatP } from './meta-reading';

const RATIO = ['OR', 'RR'];

/** Several time points of one outcome together, the study as cluster (rma.mv, P2). */
@Component({
  selector: 'rm-multilevel-card',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <h3>
      {{ 'meta.ml.title' | transloco }}
      <span class="term" tabindex="0" [matTooltip]="'meta.ml.help' | transloco">?</span>
    </h3>
    <div class="row">
      <mat-form-field subscriptSizing="dynamic" class="wide">
        <mat-label>{{ 'meta.ml.timepoints' | transloco }}</mat-label>
        <mat-select multiple [(ngModel)]="chosen">
          @for (t of timepoints(); track t) {
            <mat-option [value]="t">{{ t }}</mat-option>
          }
        </mat-select>
      </mat-form-field>
      <button
        mat-stroked-button
        type="button"
        [disabled]="busy() || chosen.length < 2"
        (click)="runIt()"
      >
        {{ 'meta.ml.run' | transloco }}
      </button>
    </div>
    <rm-form-error [error]="error()" />
    @if (out(); as o) {
      @if (o.warnings.includes('fewer_than_five_studies')) {
        <p class="notice notice-warn" role="status">{{ 'meta.ml.few' | transloco }}</p>
      }
      <p>
        <strong>{{ o.measure }}</strong> {{ shown(o, 'estimate') }} ({{ 'meta.res.ci' | transloco }}
        {{ shown(o, 'ci_lb') }} {{ 'meta.res.to' | transloco }} {{ shown(o, 'ci_ub') }}); p
        {{ p(pooled(o)['p_value']) }}
      </p>
      <p>
        {{ 'meta.ml.counts' | transloco: { k: o.k, studies: o.studies } }} ·
        {{
          'meta.ml.variance'
            | transloco
              : {
                  between: num(variance(o)['between_studies']),
                  within: num(variance(o)['within_studies']),
                }
        }}
      </p>
    }
  `,
})
export class MultilevelCard {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly context = inject(ProjectContext);

  readonly outcomeId = input<string | null>(null);
  readonly timepoints = input<string[]>([]);
  readonly measure = input<string | null>(null);

  protected chosen: string[] = [];
  protected readonly out = signal<MultilevelOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  protected pooled(o: MultilevelOut): Record<string, unknown> {
    return (o.result['pooled'] ?? {}) as Record<string, unknown>;
  }

  protected variance(o: MultilevelOut): Record<string, unknown> {
    return (o.result['variance'] ?? {}) as Record<string, unknown>;
  }

  protected shown(o: MultilevelOut, key: string): string {
    const pooled = this.pooled(o);
    const source = RATIO.includes(o.measure)
      ? ((pooled['exp'] ?? {}) as Record<string, unknown>)
      : pooled;
    return this.num(source[key], 2);
  }

  protected num(v: unknown, digits = 3): string {
    return formatNumber(
      typeof v === 'number' ? v : undefined,
      this.transloco.getActiveLang(),
      digits,
    );
  }

  protected p(v: unknown): string {
    return formatP(typeof v === 'number' ? v : undefined, this.transloco.getActiveLang());
  }

  async runIt(): Promise<void> {
    const outcome = this.outcomeId();
    if (!outcome) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      this.out.set(
        await this.api.invoke(runMultilevel, {
          project_id: this.context.project()!.id,
          body: {
            outcome_id: outcome,
            timepoints: this.chosen,
            measure: (this.measure() as 'MD' | 'SMD' | 'OR' | 'RR' | 'RD' | null) ?? null,
          },
        }),
      );
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }
}
