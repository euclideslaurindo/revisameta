import { Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { runMetaRegression } from '../../core/api/fn/analysis/run-meta-regression';
import { FormField } from '../../core/api/models/form-field';
import { MetaRegressionOut } from '../../core/api/models/meta-regression-out';
import { RunIn } from '../../core/api/models/run-in';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { formatNumber, formatP } from './meta-reading';

const RATIO = ['OR', 'RR'];

/** Meta-regression (P2): moderators from the extraction form, computed by R. */
@Component({
  selector: 'rm-meta-regression-card',
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
      {{ 'meta.mr.title' | transloco }}
      <span class="term" tabindex="0" [matTooltip]="'meta.mr.help' | transloco">?</span>
    </h3>
    <div class="row">
      <mat-form-field subscriptSizing="dynamic" class="wide">
        <mat-label>{{ 'meta.mr.moderators' | transloco }}</mat-label>
        <mat-select multiple [(ngModel)]="chosen">
          <mat-option value="cutoff_used">{{ 'meta.sub.byCutoff' | transloco }}</mat-option>
          @for (f of fields(); track f.key) {
            <mat-option [value]="f.key">{{ label(f) }}</mat-option>
          }
        </mat-select>
      </mat-form-field>
      <button
        mat-stroked-button
        type="button"
        [disabled]="busy() || !chosen.length"
        (click)="runIt()"
      >
        {{ 'meta.mr.run' | transloco }}
      </button>
    </div>
    <rm-form-error [error]="error()" />
    @if (out(); as o) {
      @if (o.warnings.includes('fewer_than_ten_studies_per_moderator')) {
        <p class="notice notice-error" role="alert">
          <strong>{{ 'meta.mr.fewTitle' | transloco: { k: o.result['k'] } }}</strong>
          {{ 'meta.mr.few' | transloco }}
        </p>
      }
      <table class="result-table">
        <thead>
          <tr>
            <th scope="col">{{ 'meta.mr.term' | transloco }}</th>
            <th scope="col">{{ 'meta.mr.coef' | transloco }} ({{ 'meta.res.ci' | transloco }})</th>
            <th scope="col">{{ 'meta.res.p' | transloco }}</th>
          </tr>
        </thead>
        <tbody>
          @for (c of coefficients(o); track c['term']) {
            <tr>
              <td>{{ c['term'] === 'intrcpt' ? ('meta.mr.intercept' | transloco) : c['term'] }}</td>
              <td>
                {{ num(c['estimate']) }} ({{ num(c['ci_lb']) }} {{ 'meta.res.to' | transloco }}
                {{ num(c['ci_ub']) }})
              </td>
              <td>{{ p(c['p_value']) }}</td>
            </tr>
          }
        </tbody>
      </table>
      <p>
        {{
          'meta.mr.test' | transloco: { stat: num(mods(o)['statistic']), p: p(mods(o)['p_value']) }
        }}
        ·
        {{
          'meta.mr.residual'
            | transloco: { tau2: num(resid(o)['tau2'], 3), i2: num(resid(o)['i2'], 1) }
        }}
      </p>
      @if (ratio(o)) {
        <p class="muted small">{{ 'meta.mr.logScale' | transloco }}</p>
      }
      @if (o.left_out.length) {
        <p class="muted">{{ 'meta.mr.leftOut' | transloco: { studies: o.left_out.join(', ') } }}</p>
      }
    }
  `,
})
export class MetaRegressionCard {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly context = inject(ProjectContext);

  readonly analysis = input.required<RunIn>();
  readonly fields = input<FormField[]>([]);

  protected chosen: string[] = [];
  protected readonly out = signal<MetaRegressionOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  private lang(): string {
    return this.transloco.getActiveLang();
  }

  protected label(f: FormField): string {
    return f.label || (f.label_key ? this.transloco.translate(f.label_key) : f.key);
  }

  protected num(v: unknown, digits = 3): string {
    return formatNumber(typeof v === 'number' ? v : undefined, this.lang(), digits);
  }

  protected p(v: unknown): string {
    return formatP(typeof v === 'number' ? v : undefined, this.lang());
  }

  protected coefficients(o: MetaRegressionOut): Record<string, unknown>[] {
    return (o.result['coefficients'] ?? []) as Record<string, unknown>[];
  }

  protected mods(o: MetaRegressionOut): Record<string, unknown> {
    return (o.result['moderators'] ?? {}) as Record<string, unknown>;
  }

  protected resid(o: MetaRegressionOut): Record<string, unknown> {
    return (o.result['residual'] ?? {}) as Record<string, unknown>;
  }

  protected ratio(o: MetaRegressionOut): boolean {
    return RATIO.includes(o.measure);
  }

  async runIt(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.out.set(
        await this.api.invoke(runMetaRegression, {
          project_id: this.context.project()!.id,
          body: { ...this.analysis(), moderators: this.chosen },
        }),
      );
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }
}
