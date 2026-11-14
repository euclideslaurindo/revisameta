import { Component, computed, inject, input, output, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { decideDivergence } from '../../core/api/fn/extraction/decide-divergence';
import { ItemOut } from '../../core/api/models/item-out';
import { FormError } from '../../shared/form-error';
import { fieldLabel, formatValue, placeLabel } from './comparison-format';

/** One divergence: both extractors' values and sources, the consensus value and the decision. */
@Component({
  selector: 'rm-divergence-item',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
  ],
  template: `
    @let it = current();
    <div class="divergence" [class.decided]="!!it.decision">
      <div class="muted">{{ place() }}</div>
      <h4>{{ label() }}</h4>
      <div class="divergence-grid">
        <div>
          <div class="muted">{{ 'consensus.extractor' | transloco: { name: nameA() } }}</div>
          <strong>{{ show(it.value_a) }}</strong>
          @if (it.source_a; as s) {
            <div class="source">{{ sourceText(s) }}</div>
          }
        </div>
        <div>
          <div class="muted">{{ 'consensus.extractor' | transloco: { name: nameB() } }}</div>
          <strong>{{ show(it.value_b) }}</strong>
          @if (it.source_b; as s) {
            <div class="source">{{ sourceText(s) }}</div>
          }
        </div>
        <div>
          <div class="muted">{{ 'consensus.consensusValue' | transloco }}</div>
          <strong>{{ hasConsensus() ? show(it.consensus_value) : '…' }}</strong>
        </div>
      </div>
      @if (it.decision; as d) {
        <p class="decision">
          {{
            'consensus.decided.' + d.choice
              | transloco: { name: d.choice === 'a' ? nameA() : nameB() }
          }}
          @if (d.reason) {
            — {{ d.reason }}
          }
          <span class="muted">({{ d.decided_by_name }})</span>
        </p>
      }
      @if (editable()) {
        <div class="actions">
          <button mat-stroked-button type="button" [disabled]="busy()" (click)="decide('a')">
            {{ 'consensus.useValueOf' | transloco: { name: nameA() } }}
          </button>
          <button mat-stroked-button type="button" [disabled]="busy()" (click)="decide('b')">
            {{ 'consensus.useValueOf' | transloco: { name: nameB() } }}
          </button>
          <button mat-button type="button" [disabled]="busy()" (click)="keeping.set(!keeping())">
            {{ 'consensus.keepConsensus' | transloco }}
          </button>
        </div>
        @if (keeping()) {
          <div class="row">
            <mat-form-field subscriptSizing="dynamic" class="wide">
              <mat-label>{{ 'consensus.reason' | transloco }}</mat-label>
              <input matInput [(ngModel)]="reason" />
            </mat-form-field>
            <button mat-flat-button type="button" [disabled]="busy()" (click)="decide('consensus')">
              {{ 'common.confirm' | transloco }}
            </button>
          </div>
        }
      }
      <rm-form-error [error]="error()" />
    </div>
  `,
})
export class DivergenceItem {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: 'pt-BR' });

  readonly projectId = input.required<string>();
  readonly studyId = input.required<string>();
  readonly item = input.required<ItemOut>();
  readonly nameA = input('A');
  readonly nameB = input('B');
  readonly outcomeName = input<(id: string) => string>(() => '');
  readonly hasConsensus = input(false);
  readonly editable = input(false);
  readonly decided = output<ItemOut>();

  // The page reloads the comparison after each decision (one decision may settle
  // several items, e.g. the whole dispersion group), so the item is always fresh.
  protected readonly current = computed(() => this.item());
  protected readonly busy = signal(false);
  protected readonly keeping = signal(false);
  protected readonly error = signal<unknown>(null);
  protected reason = '';

  private t = (key: string, params?: Record<string, unknown>) => {
    this.lang();
    return this.transloco.translate(key, params);
  };

  protected label(): string {
    return fieldLabel(this.current(), this.t);
  }

  protected place(): string {
    return placeLabel(this.current(), this.outcomeName(), this.t);
  }

  protected show(value: unknown): string {
    return formatValue(this.current(), value, this.lang(), this.t);
  }

  protected sourceText(source: Record<string, unknown>): string {
    const parts = [source['location'], source['dispersion_source']].filter((p) => !!p) as string[];
    if (source['annotation_id']) parts.push(this.t('consensus.markedPassage'));
    return parts.length ? parts.join(' · ') : this.t('consensus.noSource');
  }

  async decide(choice: 'a' | 'b' | 'consensus'): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const result = await this.api.invoke(decideDivergence, {
        project_id: this.projectId(),
        study_id: this.studyId(),
        body: { key: this.item().key, choice, reason: choice === 'consensus' ? this.reason : null },
      });
      this.keeping.set(false);
      this.decided.emit(result);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
