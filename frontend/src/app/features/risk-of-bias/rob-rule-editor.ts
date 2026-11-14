import { Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { setRobOverallRule } from '../../core/api/fn/risk-of-bias/set-rob-overall-rule';
import { ToolOut } from '../../core/api/models/tool-out';
import { FormError } from '../../shared/form-error';
import { localized } from './rob-tool-editor';

/** Level sets the group can choose from (no free text, so outputs stay translatable). */
export const LEVEL_SETS: string[][] = [
  ['low', 'moderate', 'high'],
  ['low', 'high'],
  ['good', 'fair', 'poor'],
];

interface CaseForm {
  then: string;
  kind: 'count' | 'stars';
  answers: string[];
  atLeast: number;
  questions: string[];
}

interface RuleShape {
  levels: string[];
  cases: {
    then: string;
    count?: { answers: string[]; at_least: number; questions: string[] };
    stars_at_least?: number;
  }[];
  else: string;
}

/**
 * The group's rule for the overall judgement of JBI, Newcastle-Ottawa or generic tools:
 * cases checked in order (count of answers, or total stars for NOS), then a default.
 */
@Component({
  selector: 'rm-rob-rule-editor',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    FormError,
  ],
  template: `
    <h4>{{ 'rob.rule.title' | transloco }}</h4>
    <p class="muted">{{ 'rob.rule.hint' | transloco }}</p>
    <mat-form-field subscriptSizing="dynamic" class="wide">
      <mat-label>{{ 'rob.rule.levels' | transloco }}</mat-label>
      <mat-select [(ngModel)]="levelSet" (ngModelChange)="onLevels()">
        @for (set of levelSets; track $index) {
          <mat-option [value]="$index">{{ setLabel(set) }}</mat-option>
        }
      </mat-select>
    </mat-form-field>

    @for (c of cases; track $index) {
      <div class="rule-case">
        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'rob.rule.then' | transloco }}</mat-label>
            <mat-select [(ngModel)]="c.then">
              @for (l of levels(); track l) {
                <mat-option [value]="l">{{ 'rob.judgement.' + l | transloco }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          @if (isNos()) {
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'rob.rule.kind' | transloco }}</mat-label>
              <mat-select [(ngModel)]="c.kind">
                <mat-option value="stars">{{ 'rob.rule.kindStars' | transloco }}</mat-option>
                <mat-option value="count">{{ 'rob.rule.kindCount' | transloco }}</mat-option>
              </mat-select>
            </mat-form-field>
          }
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{
              (c.kind === 'stars' ? 'rob.rule.starsAtLeast' : 'rob.rule.atLeast') | transloco
            }}</mat-label>
            <input matInput type="number" min="0" max="100" [(ngModel)]="c.atLeast" />
          </mat-form-field>
          <button mat-button type="button" (click)="cases.splice($index, 1)">
            {{ 'common.delete' | transloco }}
          </button>
        </div>
        @if (c.kind === 'count') {
          <div class="row">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'rob.rule.answers' | transloco }}</mat-label>
              <mat-select multiple [(ngModel)]="c.answers">
                @for (a of answerOptions(); track a) {
                  <mat-option [value]="a">{{ 'rob.answer.' + a | transloco }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <mat-form-field subscriptSizing="dynamic" class="wide">
              <mat-label>{{ 'rob.rule.questions' | transloco }}</mat-label>
              <mat-select multiple [(ngModel)]="c.questions">
                @for (q of questionOptions(); track q.key) {
                  <mat-option [value]="q.key">{{ q.label }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
          </div>
        }
      </div>
    }
    <button mat-stroked-button type="button" (click)="addCase()">
      {{ 'rob.rule.addCase' | transloco }}
    </button>
    <mat-form-field subscriptSizing="dynamic">
      <mat-label>{{ 'rob.rule.else' | transloco }}</mat-label>
      <mat-select [(ngModel)]="elseLevel">
        @for (l of levels(); track l) {
          <mat-option [value]="l">{{ 'rob.judgement.' + l | transloco }}</mat-option>
        }
      </mat-select>
    </mat-form-field>
    <rm-form-error [error]="error()" />
    <div class="actions">
      <button mat-flat-button type="button" [disabled]="busy()" (click)="save()">
        {{ 'rob.rule.save' | transloco }}
      </button>
      @if (tool().overall_rule) {
        <button mat-button type="button" [disabled]="busy()" (click)="remove()">
          {{ 'rob.rule.remove' | transloco }}
        </button>
      }
      <button mat-button type="button" (click)="closed.emit()">
        {{ 'common.cancel' | transloco }}
      </button>
    </div>
  `,
})
export class RobRuleEditor implements OnInit {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: 'pt-BR' });

  readonly projectId = input.required<string>();
  readonly tool = input.required<ToolOut>();
  readonly saved = output<ToolOut>();
  readonly closed = output<void>();

  protected readonly levelSets = LEVEL_SETS;
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly levels = signal<string[]>(LEVEL_SETS[0]);
  protected levelSet = 0;
  protected cases: CaseForm[] = [];
  protected elseLevel = 'low';

  protected readonly isNos = computed(() => this.tool().family === 'nos');
  protected readonly answerOptions = computed(() => {
    const sets = (this.tool().structure['answer_sets'] ?? {}) as Record<string, string[]>;
    return [...new Set(Object.values(sets).flat())].filter((a) => !/^\d+$/.test(a));
  });
  protected readonly questionOptions = computed(() => {
    const domains = (this.tool().structure['domains'] ?? []) as {
      key: string;
      name: Record<string, string>;
      questions: { key: string; label?: string }[];
    }[];
    return domains.flatMap((d) =>
      d.questions.map((q) => ({
        key: `${d.key}.${q.key}`,
        label: `${q.label ?? q.key} · ${localized(d.name, this.lang())}`,
      })),
    );
  });

  ngOnInit(): void {
    const rule = this.tool().overall_rule as RuleShape | null | undefined;
    if (rule) {
      const index = LEVEL_SETS.findIndex((s) => s.join() === rule.levels.join());
      this.levelSet = index >= 0 ? index : 0;
      this.levels.set(rule.levels);
      this.elseLevel = rule.else;
      this.cases = rule.cases.map((c) =>
        c.count
          ? {
              then: c.then,
              kind: 'count',
              answers: c.count.answers,
              atLeast: c.count.at_least,
              questions: c.count.questions,
            }
          : {
              then: c.then,
              kind: 'stars',
              answers: [],
              atLeast: c.stars_at_least ?? 0,
              questions: [],
            },
      );
    } else {
      this.levelSet = this.isNos() ? 2 : 0;
      this.onLevels();
    }
  }

  protected setLabel(set: string[]): string {
    this.lang();
    return set.map((l) => this.transloco.translate('rob.judgement.' + l)).join(' / ');
  }

  protected onLevels(): void {
    const levels = LEVEL_SETS[this.levelSet];
    this.levels.set(levels);
    this.elseLevel = this.isNos() ? levels[levels.length - 1] : levels[0];
    for (const c of this.cases) if (!levels.includes(c.then)) c.then = levels[levels.length - 1];
  }

  protected addCase(): void {
    const levels = this.levels();
    this.cases.push({
      then: this.isNos() ? levels[0] : levels[levels.length - 1],
      kind: this.isNos() ? 'stars' : 'count',
      answers: this.isNos() ? [] : ['N', 'U'],
      atLeast: 1,
      questions: [],
    });
  }

  private async send(rule: RuleShape | null): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.saved.emit(
        await this.api.invoke(setRobOverallRule, {
          project_id: this.projectId(),
          tool_id: this.tool().id,
          body: {
            version: this.tool().version,
            rule: rule as unknown as Record<string, unknown> | null,
          },
        }),
      );
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }

  async save(): Promise<void> {
    await this.send({
      levels: this.levels(),
      cases: this.cases.map((c) =>
        c.kind === 'stars'
          ? { then: c.then, stars_at_least: Number(c.atLeast) }
          : {
              then: c.then,
              count: { answers: c.answers, at_least: Number(c.atLeast), questions: c.questions },
            },
      ),
      else: this.elseLevel,
    });
  }

  async remove(): Promise<void> {
    await this.send(null);
  }
}
