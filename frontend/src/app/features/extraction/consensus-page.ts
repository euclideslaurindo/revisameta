import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { createConsensus } from '../../core/api/fn/extraction/create-consensus';
import { studyComparison } from '../../core/api/fn/extraction/study-comparison';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { getStudy } from '../../core/api/fn/studies/get-study';
import { ComparisonOut } from '../../core/api/models/comparison-out';
import { ItemOut } from '../../core/api/models/item-out';
import { FormError } from '../../shared/form-error';
import { displayDecimal } from '../../shared/numbers';
import { ProjectContext } from '../project/project-context';
import { fieldLabel, formatValue, placeLabel } from './comparison-format';
import { DivergenceItem } from './divergence-item';

/**
 * Block D: what the two extractors typed, side by side. The admin creates the
 * consensus and settles each divergence; texts are shown but never diverge.
 */
@Component({
  selector: 'rm-consensus-page',
  imports: [
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatTooltipModule,
    FormError,
    DivergenceItem,
  ],
  template: `
    <a [routerLink]="['/projetos', projectId(), 'estudos', studyId()]">← {{ studyLabel() }}</a>
    <h2>{{ 'consensus.title' | transloco: { study: studyLabel() } }}</h2>
    <p class="muted">{{ 'consensus.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />

    @if (data(); as c) {
      @if (c.submitted < 2 && c.double_extraction) {
        <p class="notice">
          {{ 'consensus.waiting' | transloco: { submitted: c.submitted, needed: c.needed } }}
        </p>
      }
      @if (!c.double_extraction) {
        <p class="notice">{{ 'consensus.single' | transloco }}</p>
      }

      @if (c.submitted >= 2) {
        <mat-card class="block">
          <mat-card-header>
            <mat-card-title>
              <h3>
                {{ 'consensus.agreement.title' | transloco }}
                <span class="term" tabindex="0" [matTooltip]="'glossary.agreement' | transloco"
                  >?</span
                >
              </h3>
            </mat-card-title>
          </mat-card-header>
          <mat-card-content>
            @if (c.agreement; as a) {
              <p>
                {{
                  'consensus.agreement.percent'
                    | transloco
                      : {
                          percent: number(a.agreement_percent, 1),
                          agreeing: a.agreeing_items,
                          items: a.items,
                        }
                }}
              </p>
              <p>
                @if (a.kappa !== null && a.kappa !== undefined) {
                  {{
                    'consensus.agreement.kappa'
                      | transloco: { kappa: number(a.kappa, 2), items: a.kappa_items }
                  }}
                } @else {
                  {{ 'consensus.agreement.noKappa' | transloco }}
                }
                <span class="term" tabindex="0" [matTooltip]="'glossary.kappa' | transloco">?</span>
              </p>
            } @else if (c.agreement_error) {
              <p class="notice notice-error">{{ 'consensus.agreement.unavailable' | transloco }}</p>
            }
            <p>
              {{
                'consensus.counts'
                  | transloco: { divergences: c.divergences, undecided: c.undecided }
              }}
            </p>
            @if (c.consensus; as cons) {
              <a mat-flat-button [routerLink]="['/projetos', projectId(), 'extracoes', cons.id]">
                {{ 'consensus.open' | transloco }}
              </a>
              <span class="badge">{{ 'extraction.status.' + cons.status | transloco }}</span>
            } @else {
              <p class="muted">{{ 'consensus.createHint' | transloco }}</p>
              <button mat-flat-button type="button" [disabled]="busy()" (click)="create()">
                {{ 'consensus.create' | transloco }}
              </button>
            }
          </mat-card-content>
        </mat-card>

        <h3>{{ 'consensus.divergences' | transloco }}</h3>
        @if (divergent().length === 0) {
          <p class="empty">{{ 'consensus.noDivergences' | transloco }}</p>
        }
        @for (item of divergent(); track item.key) {
          <rm-divergence-item
            [projectId]="projectId()"
            [studyId]="studyId()"
            [item]="item"
            [nameA]="nameA()"
            [nameB]="nameB()"
            [outcomeName]="outcomeName"
            [hasConsensus]="!!c.consensus"
            [editable]="c.consensus?.status === 'draft'"
            (decided)="load()"
          />
        }

        @if (texts().length > 0) {
          <h3>{{ 'consensus.texts' | transloco }}</h3>
          <p class="muted">{{ 'consensus.textsHint' | transloco }}</p>
          <ul class="item-list">
            @for (item of texts(); track item.key) {
              <li>
                <div>
                  <div class="muted">{{ place(item) }} · {{ label(item) }}</div>
                  <div>{{ nameA() }}: {{ show(item, item.value_a) }}</div>
                  <div>{{ nameB() }}: {{ show(item, item.value_b) }}</div>
                </div>
              </li>
            }
          </ul>
        }
      }
    }
  `,
})
export class ConsensusPage {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: 'pt-BR' });

  readonly studyId = input.required<string>();

  protected readonly data = signal<ComparisonOut | null>(null);
  protected readonly studyLabel = signal('');
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  private readonly outcomes = signal<Record<string, string>>({});

  protected readonly divergent = computed(() =>
    (this.data()?.items ?? []).filter((i) => i.divergent),
  );
  protected readonly texts = computed(() =>
    (this.data()?.items ?? []).filter((i) => i.kind === 'text' && !i.agree),
  );
  protected readonly nameA = computed(() => this.extractorName('a'));
  protected readonly nameB = computed(() => this.extractorName('b'));
  protected readonly outcomeName = (id: string) => this.outcomes()[id] ?? '';

  constructor() {
    effect(() => {
      const id = this.studyId();
      void this.init(id);
    });
  }

  protected projectId(): string {
    return this.context.project()!.id;
  }

  private t = (key: string, params?: Record<string, unknown>) => {
    this.lang();
    return this.transloco.translate(key, params);
  };

  private extractorName(side: string): string {
    const e = this.data()?.extractors.find((x) => x.side === side);
    return e?.name ?? side.toUpperCase();
  }

  protected number(value: number, digits: number): string {
    return displayDecimal(value.toFixed(digits), this.lang());
  }

  protected label(item: ItemOut): string {
    return fieldLabel(item, this.t);
  }

  protected place(item: ItemOut): string {
    return placeLabel(item, this.outcomeName, this.t);
  }

  protected show(item: ItemOut, value: unknown): string {
    return formatValue(item, value, this.lang(), this.t);
  }

  private async init(studyId: string): Promise<void> {
    const project_id = this.projectId();
    try {
      const [study, outcomes] = await Promise.all([
        this.api.invoke(getStudy, { project_id, study_id: studyId }),
        this.api.invoke(listOutcomes, { project_id }),
      ]);
      this.studyLabel.set(study.label);
      this.outcomes.set(Object.fromEntries(outcomes.map((o) => [o.id, o.name])));
      await this.load();
    } catch (error) {
      this.error.set(error);
    }
  }

  async load(): Promise<void> {
    try {
      this.data.set(
        await this.api.invoke(studyComparison, {
          project_id: this.projectId(),
          study_id: this.studyId(),
        }),
      );
    } catch (error) {
      this.error.set(error);
    }
  }

  async create(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.invoke(createConsensus, {
        project_id: this.projectId(),
        study_id: this.studyId(),
      });
      await this.load();
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
