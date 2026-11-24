import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { createRobConsensus } from '../../core/api/fn/risk-of-bias/create-rob-consensus';
import { decideRobConflict } from '../../core/api/fn/risk-of-bias/decide-rob-conflict';
import { listRobComparisons } from '../../core/api/fn/risk-of-bias/list-rob-comparisons';
import { listRobTools } from '../../core/api/fn/risk-of-bias/list-rob-tools';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { getStudy } from '../../core/api/fn/studies/get-study';
import { RobComparisonOut } from '../../core/api/models/rob-comparison-out';
import { RobItemOut } from '../../core/api/models/rob-item-out';
import { ToolOut } from '../../core/api/models/tool-out';
import { FormError } from '../../shared/form-error';
import { displayDecimal } from '../../shared/numbers';
import { ProjectContext } from '../project/project-context';
import { localized } from './rob-tool-editor';

interface DomainView {
  key: string;
  name: Record<string, string>;
  questions: { key: string; label?: string }[];
  variants?: { key: string; name: Record<string, string> }[];
}

/**
 * The two risk-of-bias assessments of a study side by side (admins only). The admin
 * starts the consensus from reviewer A and settles each conflict; whoever decides is
 * recorded, and keeping a third value needs a short reason.
 */
@Component({
  selector: 'rm-rob-consensus-page',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <a [routerLink]="['/projetos', projectId(), 'estudos', studyId()]">← {{ studyLabel() }}</a>
    <h2>{{ 'rob.consensus.title' | transloco: { study: studyLabel() } }}</h2>
    <p class="muted">{{ 'rob.consensus.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />
    @if (loaded() && comparisons().length === 0) {
      <p class="empty">{{ 'rob.consensus.none' | transloco }}</p>
    }

    @for (c of comparisons(); track $index) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title>
            <h3>
              {{ toolName(c.tool_id) }}
              @if (c.timepoint) {
                · {{ outcomeName(c.outcome_id) }} · {{ c.timepoint }}
              }
            </h3>
          </mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <p>
            @for (r of c.reviewers; track r.assessment_id) {
              <span class="badge"
                >{{ r.side ? r.side.toUpperCase() + ': ' : '' }}{{ r.name }} ·
                {{ 'extraction.status.' + r.status | transloco }}</span
              >
            }
          </p>
          @if (c.submitted < (c.needed ?? 2)) {
            <p class="notice">
              {{ 'rob.consensus.waiting' | transloco: { submitted: c.submitted } }}
            </p>
          } @else {
            @if (c.submitted < 2) {
              <p class="notice">{{ 'rob.consensus.single' | transloco }}</p>
            }
            @if (c.agreement; as a) {
              <p>
                {{
                  'rob.consensus.agreement'
                    | transloco
                      : {
                          percent: number(a.agreement_percent, 1),
                          agreeing: a.agreeing_items,
                          items: a.items,
                        }
                }}
                @if (a.kappa !== null && a.kappa !== undefined) {
                  · {{ 'rob.consensus.kappa' | transloco: { kappa: number(a.kappa, 2) } }}
                }
                <span class="term" tabindex="0" [matTooltip]="'glossary.robKappa' | transloco"
                  >?</span
                >
              </p>
            } @else if (c.agreement_error) {
              <p class="notice notice-error">{{ 'consensus.agreement.unavailable' | transloco }}</p>
            }
            <p>
              {{
                'rob.consensus.counts'
                  | transloco: { conflicts: c.divergences, undecided: c.undecided }
              }}
            </p>
            @if (c.consensus; as cons) {
              <a
                mat-flat-button
                [routerLink]="['/projetos', projectId(), 'risco-de-vies', 'avaliacoes', cons.id]"
              >
                {{ 'rob.consensus.open' | transloco }}
              </a>
              <span class="badge">{{ 'extraction.status.' + cons.status | transloco }}</span>
            } @else {
              <p class="muted">{{ 'rob.consensus.createHint' | transloco }}</p>
              <button mat-flat-button type="button" [disabled]="busy()" (click)="create(c)">
                {{ 'rob.consensus.create' | transloco }}
              </button>
            }

            <h4>{{ 'rob.consensus.conflicts' | transloco }}</h4>
            @for (item of conflicts(c); track item.key) {
              <div class="rob-question-block">
                <div>
                  <strong>{{ itemLabel(c, item) }}</strong>
                </div>
                <div class="compare-grid">
                  <div>
                    <div class="muted">A · {{ reviewerName(c, 'a') }}</div>
                    <div>{{ valueLabel(c, item, item.value_a) }}</div>
                    @if (item.justification_a) {
                      <div class="muted">“{{ item.justification_a }}”</div>
                    }
                  </div>
                  <div>
                    <div class="muted">B · {{ reviewerName(c, 'b') }}</div>
                    <div>{{ valueLabel(c, item, item.value_b) }}</div>
                    @if (item.justification_b) {
                      <div class="muted">“{{ item.justification_b }}”</div>
                    }
                  </div>
                  @if (c.consensus) {
                    <div>
                      <div class="muted">{{ 'rob.consensus.value' | transloco }}</div>
                      <div>{{ valueLabel(c, item, item.consensus_value) }}</div>
                    </div>
                  }
                </div>
                @if (item.decision; as d) {
                  <p class="notice">
                    {{
                      'rob.consensus.decided.' + d.choice
                        | transloco: { name: d.decided_by_name ?? '—' }
                    }}
                    @if (d.reason) {
                      — {{ d.reason }}
                    }
                  </p>
                }
                @if (c.consensus?.status === 'draft') {
                  <div class="actions">
                    <button
                      mat-stroked-button
                      type="button"
                      [disabled]="busy()"
                      (click)="decide(c, item, 'a')"
                    >
                      {{ 'rob.consensus.useA' | transloco }}
                    </button>
                    <button
                      mat-stroked-button
                      type="button"
                      [disabled]="busy()"
                      (click)="decide(c, item, 'b')"
                    >
                      {{ 'rob.consensus.useB' | transloco }}
                    </button>
                    <mat-form-field subscriptSizing="dynamic" class="wide">
                      <mat-label>{{ 'rob.consensus.reason' | transloco }}</mat-label>
                      <input matInput [(ngModel)]="reasons[item.key]" maxlength="1000" />
                    </mat-form-field>
                    <button
                      mat-stroked-button
                      type="button"
                      [disabled]="busy() || (reasons[item.key] ?? '').trim().length < 5"
                      (click)="decide(c, item, 'consensus')"
                    >
                      {{ 'rob.consensus.keep' | transloco }}
                    </button>
                  </div>
                }
              </div>
            } @empty {
              <p class="empty">{{ 'rob.consensus.noConflicts' | transloco }}</p>
            }
          }
        </mat-card-content>
      </mat-card>
    }
  `,
})
export class RobConsensusPage {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: 'pt-BR' });

  readonly studyId = input.required<string>();
  protected readonly projectId = computed(() => this.context.project()!.id);
  protected readonly comparisons = signal<RobComparisonOut[]>([]);
  protected readonly tools = signal<ToolOut[]>([]);
  protected readonly outcomes = signal<Record<string, string>>({});
  protected readonly studyLabel = signal('');
  protected readonly loaded = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected reasons: Record<string, string> = {};

  constructor() {
    effect(() => void this.load(this.studyId()));
  }

  private async load(studyId: string): Promise<void> {
    const project_id = this.projectId();
    try {
      const [comparisons, tools, study, outcomes] = await Promise.all([
        this.api.invoke(listRobComparisons, { project_id, study_id: studyId }),
        this.api.invoke(listRobTools, { project_id }),
        this.api.invoke(getStudy, { project_id, study_id: studyId }),
        this.api.invoke(listOutcomes, { project_id }),
      ]);
      this.tools.set(tools);
      this.studyLabel.set(study.label);
      this.outcomes.set(Object.fromEntries(outcomes.map((o) => [o.id, o.name])));
      this.comparisons.set(comparisons);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.loaded.set(true);
    }
  }

  protected conflicts(c: RobComparisonOut): RobItemOut[] {
    return c.items.filter((i) => !i.agree);
  }

  protected number(value: number, digits: number): string {
    return displayDecimal(value.toFixed(digits), this.lang());
  }

  private tool(id: string): ToolOut | undefined {
    return this.tools().find((t) => t.id === id);
  }

  private domains(c: RobComparisonOut): DomainView[] {
    return (this.tool(c.tool_id)?.structure['domains'] ?? []) as DomainView[];
  }

  protected toolName(id: string): string {
    const tool = this.tool(id);
    return tool ? localized(tool.structure['name'] as Record<string, string>, this.lang()) : '';
  }

  protected outcomeName(id: string | null | undefined): string {
    return id ? (this.outcomes()[id] ?? '') : '';
  }

  protected reviewerName(c: RobComparisonOut, side: string): string {
    return c.reviewers.find((r) => r.side === side)?.name ?? '';
  }

  private t(key: string, params?: Record<string, unknown>): string {
    this.lang();
    return this.transloco.translate(key, params);
  }

  protected itemLabel(c: RobComparisonOut, item: RobItemOut): string {
    if (item.kind === 'overall') return this.t('rob.assessment.overall');
    const domain = this.domains(c).find((d) => d.key === item.domain_key);
    const domainName = domain ? localized(domain.name, this.lang()) : (item.domain_key ?? '');
    if (item.kind === 'variant') return `${domainName} · ${this.t('rob.consensus.variant')}`;
    if (item.kind === 'domain') return `${domainName} · ${this.t('rob.assessment.judgement')}`;
    const qkey = item.question_key?.split('.').slice(1).join('.') ?? '';
    const question = domain?.questions.find((q) => q.key === qkey);
    const parts = [domainName, this.t('rob.texts.question', { n: question?.label ?? qkey })];
    if (item.outcome_id) parts.push(this.outcomeName(item.outcome_id));
    if (item.timepoint) parts.push(item.timepoint);
    return parts.join(' · ');
  }

  protected valueLabel(
    c: RobComparisonOut,
    item: RobItemOut,
    value: string | null | undefined,
  ): string {
    if (!value) return this.t('rob.consensus.blank');
    if (item.kind === 'variant') {
      const domain = this.domains(c).find((d) => d.key === item.domain_key);
      const variant = domain?.variants?.find((v) => v.key === value);
      return variant ? localized(variant.name, this.lang()) : value;
    }
    const key =
      item.kind === 'answer'
        ? /^\d+$/.test(value)
          ? 'rob.answer.stars'
          : 'rob.answer.' + value
        : 'rob.judgement.' + value;
    const text = this.t(key, { n: value });
    return text === key ? value : text;
  }

  async create(c: RobComparisonOut): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.invoke(createRobConsensus, {
        project_id: this.projectId(),
        study_id: this.studyId(),
        body: { outcome_id: c.outcome_id ?? null, timepoint: c.timepoint ?? null },
      });
      await this.load(this.studyId());
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }

  async decide(
    c: RobComparisonOut,
    item: RobItemOut,
    choice: 'a' | 'b' | 'consensus',
  ): Promise<void> {
    if (!c.consensus) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const updated = await this.api.invoke(decideRobConflict, {
        project_id: this.projectId(),
        assessment_id: c.consensus.id,
        body: {
          key: item.key,
          choice,
          reason: choice === 'consensus' ? (this.reasons[item.key] ?? null) : null,
        },
      });
      this.comparisons.update((list) => list.map((x) => (x === c ? updated : x)));
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
