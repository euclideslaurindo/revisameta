import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { deleteGrade } from '../../core/api/fn/grade/delete-grade';
import { gradeAssessments } from '../../core/api/fn/grade/grade-assessments';
import { saveGrade } from '../../core/api/fn/grade/save-grade';
import { suggestGrade } from '../../core/api/fn/grade/suggest-grade';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { listRobTools } from '../../core/api/fn/risk-of-bias/list-rob-tools';
import { GradeOut } from '../../core/api/models/grade-out';
import { OutcomeOut } from '../../core/api/models/outcome-out';
import { SuggestOut } from '../../core/api/models/suggest-out';
import { ToolOut } from '../../core/api/models/tool-out';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { localized } from '../risk-of-bias/rob-tool-editor';

const DOWN = ['risk_of_bias', 'inconsistency', 'indirectness', 'imprecision', 'publication_bias'];
const UP = ['large_effect', 'dose_response', 'plausible_confounding'];
const LEVELS = ['very_low', 'low', 'moderate', 'high'];

interface Choice {
  change: number;
  justification: string;
}

/** GRADE (docs/modulos.md 7.8): the system suggests, the group decides and justifies. */
@Component({
  selector: 'rm-grade-page',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <mat-card class="block">
      <mat-card-content>
        <h2>
          {{ 'grade.title' | transloco }}
          <span class="term" tabindex="0" [matTooltip]="'grade.help' | transloco">?</span>
        </h2>
        <p>{{ 'grade.intro' | transloco }}</p>
        <rm-form-error [error]="error()" />
        <div class="row">
          <mat-form-field subscriptSizing="dynamic" class="wide">
            <mat-label>{{ 'grade.outcome' | transloco }}</mat-label>
            <mat-select [(ngModel)]="outcomeId" (ngModelChange)="timepoint = null">
              @for (o of outcomes(); track o.id) {
                <mat-option [value]="o.id">{{ o.name }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'grade.timepoint' | transloco }}</mat-label>
            <mat-select [(ngModel)]="timepoint">
              @for (t of timepoints(); track t) {
                <mat-option [value]="t">{{ t }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic" class="wide">
            <mat-label>{{ 'grade.robTool' | transloco }}</mat-label>
            <mat-select [(ngModel)]="robToolId">
              <mat-option [value]="null">{{ 'grade.robNone' | transloco }}</mat-option>
              @for (tool of robTools(); track tool.id) {
                <mat-option [value]="tool.id">{{ toolName(tool) }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <button
            mat-flat-button
            type="button"
            [disabled]="busy() || !outcomeId || !timepoint"
            (click)="suggest()"
          >
            {{ 'grade.suggest' | transloco }}
          </button>
        </div>
      </mat-card-content>
    </mat-card>

    @if (suggestion(); as s) {
      <mat-card class="block">
        <mat-card-content>
          <p>
            {{
              'grade.basis' | transloco: { k: s.k, measure: s.measure, n: s.participants ?? '—' }
            }}
          </p>
          <div class="row">
            <mat-form-field subscriptSizing="dynamic" class="wide">
              <mat-label>{{ 'grade.approach' | transloco }}</mat-label>
              <mat-select [(ngModel)]="approach">
                <mat-option value="classic">{{
                  'grade.approachName.classic' | transloco
                }}</mat-option>
                <mat-option value="robins_i">{{
                  'grade.approachName.robins_i' | transloco
                }}</mat-option>
              </mat-select>
            </mat-form-field>
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'grade.start' | transloco }}</mat-label>
              <mat-select [(ngModel)]="start">
                <mat-option value="low">{{ 'grade.level.low' | transloco }}</mat-option>
                <mat-option value="high">{{ 'grade.level.high' | transloco }}</mat-option>
              </mat-select>
            </mat-form-field>
            <span class="muted">
              {{
                (s.observational ? 'grade.startObservational' : 'grade.startRandomized') | transloco
              }}
            </span>
          </div>
          <table class="result-table">
            <thead>
              <tr>
                <th scope="col">{{ 'grade.domain' | transloco }}</th>
                <th scope="col">{{ 'grade.suggested' | transloco }}</th>
                <th scope="col">{{ 'grade.decision' | transloco }}</th>
              </tr>
            </thead>
            <tbody>
              @for (key of keys; track key) {
                <tr>
                  <td>
                    {{ 'grade.domainName.' + key | transloco }}
                    <span
                      class="term"
                      tabindex="0"
                      [matTooltip]="'grade.domainHelp.' + key | transloco"
                      >?</span
                    >
                  </td>
                  <td>
                    <strong>{{ signed(s.domains[key].suggested) }}</strong>
                    {{ 'grade.reason.' + s.domains[key].reason | transloco: values(s, key) }}
                  </td>
                  <td>
                    <div class="row">
                      <mat-form-field subscriptSizing="dynamic" class="change">
                        <mat-label>{{ 'grade.change' | transloco }}</mat-label>
                        <mat-select [(ngModel)]="choices[key].change">
                          @for (v of options(key); track v) {
                            <mat-option [value]="v">{{ signed(v) }}</mat-option>
                          }
                        </mat-select>
                      </mat-form-field>
                      <mat-form-field subscriptSizing="dynamic" class="wide">
                        <mat-label>{{ 'grade.justification' | transloco }}</mat-label>
                        <input matInput maxlength="2000" [(ngModel)]="choices[key].justification" />
                      </mat-form-field>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
          <p>
            <strong>{{ 'grade.final' | transloco }}:</strong>
            {{ 'grade.level.' + final() | transloco }}
          </p>
          <mat-form-field subscriptSizing="dynamic" class="full">
            <mat-label>{{ 'grade.note' | transloco }}</mat-label>
            <textarea matInput maxlength="2000" rows="2" [(ngModel)]="note"></textarea>
          </mat-form-field>
          @if (canEdit()) {
            <button mat-flat-button type="button" [disabled]="busy()" (click)="save()">
              {{ 'grade.save' | transloco }}
            </button>
          }
        </mat-card-content>
      </mat-card>
    }

    <mat-card class="block">
      <mat-card-content>
        <h3>{{ 'grade.saved' | transloco }}</h3>
        @if (saved().length) {
          <table class="result-table">
            <thead>
              <tr>
                <th scope="col">{{ 'grade.outcome' | transloco }}</th>
                <th scope="col">{{ 'grade.timepoint' | transloco }}</th>
                <th scope="col">{{ 'grade.final' | transloco }}</th>
                <th scope="col"></th>
              </tr>
            </thead>
            <tbody>
              @for (g of saved(); track g.id) {
                <tr>
                  <td>{{ g.outcome_name }}</td>
                  <td>{{ g.timepoint }}</td>
                  <td>{{ 'grade.level.' + g.final_certainty | transloco }}</td>
                  <td>
                    <button mat-button type="button" (click)="open(g)">
                      {{ 'grade.open' | transloco }}
                    </button>
                    @if (canEdit()) {
                      <button mat-button type="button" (click)="remove(g)">
                        {{ 'grade.remove' | transloco }}
                      </button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <p class="muted">{{ 'grade.empty' | transloco }}</p>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .change {
      width: 110px;
    }
    .full {
      width: 100%;
    }
  `,
})
export class GradePage implements OnInit {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly context = inject(ProjectContext);

  protected readonly keys = [...DOWN, ...UP];
  protected readonly outcomes = signal<OutcomeOut[]>([]);
  protected readonly robTools = signal<ToolOut[]>([]);
  protected readonly saved = signal<GradeOut[]>([]);
  protected readonly suggestion = signal<SuggestOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly tick = signal(0);
  protected readonly canEdit = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.some((r) => r === 'admin' || r === 'reviewer' || r === 'statistician');
  });

  protected outcomeId: string | null = null;
  protected timepoint: string | null = null;
  protected robToolId: string | null = null;
  protected approach: 'classic' | 'robins_i' = 'classic';
  protected start: 'low' | 'high' = 'low';
  protected note = '';
  protected choices: Record<string, Choice> = {};
  private version: number | null = null;

  protected timepoints(): string[] {
    return this.outcomes().find((o) => o.id === this.outcomeId)?.timepoints ?? [];
  }

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    const project_id = this.projectId();
    await this.guard(async () => {
      const [outcomes, tools] = await Promise.all([
        this.api.invoke(listOutcomes, { project_id }),
        this.api.invoke(listRobTools, { project_id }),
      ]);
      this.outcomes.set(outcomes);
      this.robTools.set(tools);
      this.outcomeId = outcomes[0]?.id ?? null;
      this.timepoint = outcomes[0]?.timepoints[0] ?? null;
      await this.loadSaved();
    });
  }

  private async loadSaved(): Promise<void> {
    this.saved.set(await this.api.invoke(gradeAssessments, { project_id: this.projectId() }));
  }

  protected toolName(tool: ToolOut): string {
    return localized(
      tool.structure['name'] as Record<string, string>,
      this.transloco.getActiveLang(),
    );
  }

  protected signed(v: number): string {
    return v > 0 ? `+${v}` : `${v}`;
  }

  protected options(key: string): number[] {
    if (DOWN.includes(key)) return [0, -1, -2];
    return key === 'large_effect' ? [0, 1, 2] : [0, 1];
  }

  protected values(s: SuggestOut, key: string): Record<string, unknown> {
    const v = { ...(s.domains[key].values ?? {}) } as Record<string, unknown>;
    if (typeof v['i2'] === 'number') v['i2'] = (v['i2'] as number).toFixed(1);
    if (typeof v['p'] === 'number') v['p'] = (v['p'] as number).toFixed(3);
    return v;
  }

  protected final(): string {
    this.tick();
    const total = this.keys.reduce((sum, k) => sum + (this.choices[k]?.change ?? 0), 0);
    const level = LEVELS.indexOf(this.start) + total;
    return LEVELS[Math.max(0, Math.min(LEVELS.length - 1, level))];
  }

  private basis() {
    return {
      outcome_id: this.outcomeId!,
      timepoint: this.timepoint!,
      rob_tool_id: this.robToolId,
    };
  }

  async suggest(existing?: GradeOut): Promise<void> {
    await this.guard(async () => {
      const s = await this.api.invoke(suggestGrade, {
        project_id: this.projectId(),
        body: this.basis(),
      });
      this.choices = Object.fromEntries(
        this.keys.map((k) => {
          const kept = existing?.domains[k] as { change: number; justification: string | null };
          return [
            k,
            kept
              ? { change: kept.change, justification: kept.justification ?? '' }
              : { change: s.domains[k].suggested, justification: '' },
          ];
        }),
      );
      if (!existing) {
        this.start = s.start_suggested === 'high' ? 'high' : 'low';
        this.version =
          this.saved().find(
            (g) => g.outcome_id === this.outcomeId && g.timepoint === this.timepoint,
          )?.version ?? null;
      }
      this.suggestion.set(s);
    });
  }

  async open(g: GradeOut): Promise<void> {
    this.outcomeId = g.outcome_id;
    this.timepoint = g.timepoint;
    this.robToolId = (g.analysis['rob_tool_id'] as string | null) ?? null;
    this.approach = g.approach as 'classic' | 'robins_i';
    this.start = g.start_certainty as 'low' | 'high';
    this.note = g.note ?? '';
    this.version = g.version;
    await this.suggest(g);
  }

  async save(): Promise<void> {
    await this.guard(async () => {
      const out = await this.api.invoke(saveGrade, {
        project_id: this.projectId(),
        body: {
          ...this.basis(),
          approach: this.approach,
          start_certainty: this.start,
          note: this.note.trim() || null,
          version: this.version,
          domains: Object.fromEntries(
            this.keys.map((k) => [
              k,
              {
                change: this.choices[k].change,
                justification: this.choices[k].justification.trim() || null,
              },
            ]),
          ),
        },
      });
      this.version = out.version;
      await this.loadSaved();
    });
  }

  async remove(g: GradeOut): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(deleteGrade, { project_id: this.projectId(), assessment_id: g.id });
      await this.loadSaved();
    });
  }

  private async guard(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
      this.tick.update((n) => n + 1);
    }
  }
}
