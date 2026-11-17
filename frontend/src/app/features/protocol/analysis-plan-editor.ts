import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { getAnalysisPlan } from '../../core/api/fn/protocol/get-analysis-plan';
import { listGroups } from '../../core/api/fn/protocol/list-groups';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { saveAnalysisPlan } from '../../core/api/fn/protocol/save-analysis-plan';
import { GroupOut } from '../../core/api/models/group-out';
import { OutcomeOut } from '../../core/api/models/outcome-out';
import { PlanIn } from '../../core/api/models/plan-in';
import { PlanOut } from '../../core/api/models/plan-out';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

type Sensitivity = NonNullable<PlanOut['sensitivity']>[number];

export const SENSITIVITY: Sensitivity[] = [
  'leave_one_out',
  'exclude_high_risk_of_bias',
  'exclude_estimated_data',
  'fixed_vs_random',
  'other_estimator',
  'by_cutoff',
];

interface OutcomeRow {
  outcome: OutcomeOut;
  included: boolean;
  measure: string;
  timepoint: string | null;
}

/**
 * The analysis plan decided before seeing the data (7.1): who is group 1, the cut-off
 * rule, adjusted effects, measure and time point per outcome, model, sensitivity and
 * subgroups. Analyses that differ from it are marked "not planned".
 */
@Component({
  selector: 'rm-analysis-plan-editor',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <mat-card class="block">
      <mat-card-header>
        <mat-card-title>
          <h2>
            {{ 'plan.title' | transloco }}
            <span class="term" tabindex="0" [matTooltip]="'glossary.analysisPlan' | transloco"
              >?</span
            >
          </h2>
        </mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <p class="muted">{{ 'plan.intro' | transloco }}</p>
        @if (loaded() && !defined()) {
          <p class="notice">{{ 'plan.notDefined' | transloco }}</p>
        }

        <h3>{{ 'plan.comparison.title' | transloco }}</h3>
        @if (groups().length < 2) {
          <p class="muted">{{ 'plan.comparison.needGroups' | transloco }}</p>
        } @else {
          <p class="muted">{{ 'plan.comparison.hint' | transloco }}</p>
          <div class="row">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'plan.comparison.group1' | transloco }}</mat-label>
              <mat-select [(ngModel)]="group1" [disabled]="!isAdmin()">
                @for (g of groups(); track g.id) {
                  <mat-option [value]="g.id">{{ g.label }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'plan.comparison.group2' | transloco }}</mat-label>
              <mat-select [(ngModel)]="group2" [disabled]="!isAdmin()">
                @for (g of groups(); track g.id) {
                  <mat-option [value]="g.id">{{ g.label }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
          </div>
        }

        <h3>
          {{ 'plan.cutoff.title' | transloco }}
          <span class="term" tabindex="0" [matTooltip]="'plan.cutoff.help' | transloco">?</span>
        </h3>
        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'plan.cutoff.value' | transloco }}</mat-label>
            <input
              matInput
              type="number"
              min="0"
              [(ngModel)]="cutoffValue"
              [disabled]="!isAdmin()"
            />
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'plan.cutoff.unit' | transloco }}</mat-label>
            <mat-select [(ngModel)]="cutoffUnit" [disabled]="!isAdmin()">
              <mat-option value="years">{{ 'plan.cutoff.years' | transloco }}</mat-option>
              <mat-option value="months">{{ 'plan.cutoff.months' | transloco }}</mat-option>
            </mat-select>
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'plan.cutoff.rule' | transloco }}</mat-label>
            <mat-select [(ngModel)]="cutoffRule" [disabled]="!isAdmin()">
              <mat-option value="strict">{{ 'plan.cutoff.strict' | transloco }}</mat-option>
              <mat-option value="tolerant">{{ 'plan.cutoff.tolerant' | transloco }}</mat-option>
            </mat-select>
          </mat-form-field>
          @if (cutoffRule === 'tolerant') {
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'plan.cutoff.min' | transloco }}</mat-label>
              <input
                matInput
                type="number"
                min="0"
                [(ngModel)]="toleranceMin"
                [disabled]="!isAdmin()"
              />
            </mat-form-field>
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'plan.cutoff.max' | transloco }}</mat-label>
              <input
                matInput
                type="number"
                min="0"
                [(ngModel)]="toleranceMax"
                [disabled]="!isAdmin()"
              />
            </mat-form-field>
          }
        </div>
        <p class="muted">{{ 'plan.cutoff.' + cutoffRule + 'Hint' | transloco }}</p>

        <h3>
          {{ 'plan.adjusted.title' | transloco }}
          <span class="term" tabindex="0" [matTooltip]="'glossary.adjusted' | transloco">?</span>
        </h3>
        <mat-form-field subscriptSizing="dynamic" class="wide">
          <mat-label>{{ 'plan.adjusted.label' | transloco }}</mat-label>
          <mat-select [(ngModel)]="adjusted" [disabled]="!isAdmin()">
            @for (a of adjustedOptions; track a) {
              <mat-option [value]="a">{{ 'plan.adjusted.' + a | transloco }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <h3>{{ 'plan.outcomes.title' | transloco }}</h3>
        @if (rows().length === 0) {
          <p class="muted">{{ 'plan.outcomes.empty' | transloco }}</p>
        }
        @for (row of rows(); track row.outcome.id) {
          <div class="row">
            <mat-checkbox [(ngModel)]="row.included" [disabled]="!isAdmin()">{{
              row.outcome.name
            }}</mat-checkbox>
            @if (row.included) {
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'plan.outcomes.measure' | transloco }}</mat-label>
                <mat-select [(ngModel)]="row.measure" [disabled]="!isAdmin()">
                  @for (m of measures(row.outcome); track m) {
                    <mat-option [value]="m">{{ 'plan.measures.' + m | transloco }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'plan.outcomes.timepoint' | transloco }}</mat-label>
                <mat-select [(ngModel)]="row.timepoint" [disabled]="!isAdmin()">
                  <mat-option [value]="null">{{
                    'plan.outcomes.anyTimepoint' | transloco
                  }}</mat-option>
                  @for (t of row.outcome.timepoints; track t) {
                    <mat-option [value]="t">{{ t }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            }
          </div>
        }

        <h3>{{ 'plan.model.title' | transloco }}</h3>
        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'plan.model.method' | transloco }}</mat-label>
            <mat-select [(ngModel)]="method" [disabled]="!isAdmin()">
              @for (m of methods; track m) {
                <mat-option [value]="m">{{ 'plan.model.methods.' + m | transloco }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          @if (method !== 'FE') {
            <mat-checkbox [(ngModel)]="knha" [disabled]="!isAdmin()">
              {{ 'plan.model.knha' | transloco }}
            </mat-checkbox>
            <span class="term" tabindex="0" [matTooltip]="'glossary.hartungKnapp' | transloco"
              >?</span
            >
          }
        </div>

        <h3>{{ 'plan.sensitivity.title' | transloco }}</h3>
        <div class="stack">
          @for (s of sensitivityOptions; track s) {
            <mat-checkbox
              [ngModel]="sensitivity.has(s)"
              (ngModelChange)="toggle(s, $event)"
              [disabled]="!isAdmin()"
            >
              {{ 'plan.sensitivity.' + s | transloco }}
            </mat-checkbox>
          }
        </div>

        <h3>{{ 'plan.subgroups.title' | transloco }}</h3>
        <mat-form-field subscriptSizing="dynamic" class="wide">
          <mat-label>{{ 'plan.subgroups.label' | transloco }}</mat-label>
          <textarea matInput rows="2" [(ngModel)]="subgroups" [disabled]="!isAdmin()"></textarea>
          <mat-hint>{{ 'plan.subgroups.hint' | transloco }}</mat-hint>
        </mat-form-field>

        <mat-form-field subscriptSizing="dynamic" class="wide block-field">
          <mat-label>{{ 'plan.notes' | transloco }}</mat-label>
          <textarea
            matInput
            rows="2"
            [(ngModel)]="notes"
            [disabled]="!isAdmin()"
            maxlength="4000"
          ></textarea>
        </mat-form-field>

        <rm-form-error [error]="error()" />
        @if (saved()) {
          <p class="notice notice-ok" role="status">{{ 'plan.saved' | transloco }}</p>
        }
        @if (isAdmin()) {
          <div class="actions">
            <button mat-flat-button type="button" [disabled]="busy()" (click)="save()">
              {{ 'plan.save' | transloco }}
            </button>
          </div>
        }
      </mat-card-content>
    </mat-card>
  `,
})
export class AnalysisPlanEditor implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly isAdmin = computed(() => this.context.isAdmin());
  protected readonly groups = signal<GroupOut[]>([]);
  protected readonly rows = signal<OutcomeRow[]>([]);
  protected readonly loaded = signal(false);
  protected readonly defined = signal(false);
  protected readonly busy = signal(false);
  protected readonly saved = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly adjustedOptions = ['separate', 'adjusted_only', 'unadjusted_only'] as const;
  protected readonly methods = ['REML', 'DL', 'PM', 'FE'] as const;
  protected readonly sensitivityOptions = SENSITIVITY;

  private version = 0;
  protected group1: string | null = null;
  protected group2: string | null = null;
  protected cutoffValue: number | null = null;
  protected cutoffUnit: 'years' | 'months' = 'years';
  protected cutoffRule: 'strict' | 'tolerant' = 'strict';
  protected toleranceMin: number | null = null;
  protected toleranceMax: number | null = null;
  protected adjusted: PlanIn['adjusted'] = 'separate';
  protected method: 'REML' | 'DL' | 'PM' | 'FE' = 'REML';
  protected knha = true;
  protected sensitivity = new Set<Sensitivity>();
  protected subgroups = '';
  protected notes = '';

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    const project_id = this.projectId();
    try {
      const [plan, groups, outcomes] = await Promise.all([
        this.api.invoke(getAnalysisPlan, { project_id }),
        this.api.invoke(listGroups, { project_id }),
        this.api.invoke(listOutcomes, { project_id }),
      ]);
      this.groups.set(groups);
      this.apply(plan, outcomes);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.loaded.set(true);
    }
  }

  private apply(plan: PlanOut, outcomes: OutcomeOut[]): void {
    this.version = plan.version;
    this.defined.set(plan.defined);
    this.group1 = plan.comparison?.group1_id ?? this.groups()[0]?.id ?? null;
    this.group2 = plan.comparison?.group2_id ?? this.groups()[1]?.id ?? null;
    this.cutoffValue = plan.cutoff?.value ?? null;
    this.cutoffUnit = plan.cutoff?.unit ?? 'years';
    this.cutoffRule = plan.cutoff?.rule ?? 'strict';
    this.toleranceMin = plan.cutoff?.tolerance_min ?? null;
    this.toleranceMax = plan.cutoff?.tolerance_max ?? null;
    this.adjusted = plan.adjusted ?? 'separate';
    this.method = plan.model?.method ?? 'REML';
    this.knha = (plan.model?.test ?? 'knha') === 'knha';
    this.sensitivity = new Set(plan.sensitivity ?? []);
    this.subgroups = (plan.subgroups ?? []).join('\n');
    this.notes = plan.notes ?? '';
    const planned = new Map((plan.outcomes ?? []).map((o) => [o.outcome_id, o]));
    this.rows.set(
      outcomes.map((outcome) => {
        const p = planned.get(outcome.id);
        return {
          outcome,
          included: !!p || !plan.defined,
          measure: p?.measure ?? 'auto',
          timepoint: p?.timepoint ?? null,
        };
      }),
    );
  }

  protected measures(outcome: OutcomeOut): string[] {
    return outcome.type === 'continuous' ? ['auto', 'MD', 'SMD'] : ['auto', 'RR', 'OR', 'RD'];
  }

  protected toggle(item: Sensitivity, on: boolean): void {
    if (on) this.sensitivity.add(item);
    else this.sensitivity.delete(item);
  }

  async save(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    this.saved.set(false);
    const body: PlanIn = {
      version: this.version,
      comparison:
        this.group1 && this.group2 ? { group1_id: this.group1, group2_id: this.group2 } : null,
      cutoff:
        this.cutoffValue !== null && this.cutoffValue > 0
          ? {
              value: this.cutoffValue,
              unit: this.cutoffUnit,
              rule: this.cutoffRule,
              tolerance_min: this.cutoffRule === 'tolerant' ? this.toleranceMin : null,
              tolerance_max: this.cutoffRule === 'tolerant' ? this.toleranceMax : null,
            }
          : null,
      adjusted: this.adjusted,
      outcomes: this.rows()
        .filter((r) => r.included)
        .map((r) => ({
          outcome_id: r.outcome.id,
          measure: r.measure as 'auto',
          timepoint: r.timepoint,
        })),
      model: { method: this.method, test: this.method === 'FE' || !this.knha ? 'z' : 'knha' },
      sensitivity: [...this.sensitivity],
      subgroups: this.subgroups.split('\n'),
      notes: this.notes.trim() || null,
    };
    try {
      const plan = await this.api.invoke(saveAnalysisPlan, {
        project_id: this.projectId(),
        body,
      });
      this.apply(
        plan,
        this.rows().map((r) => r.outcome),
      );
      // The plan lives in the project: keep its version current for the other forms.
      const project = this.context.project();
      if (project) this.context.update({ ...project, version: plan.version });
      this.saved.set(true);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
