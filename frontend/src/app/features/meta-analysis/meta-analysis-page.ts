import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatStepperModule } from '@angular/material/stepper';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { analysisForestPlot } from '../../core/api/fn/analysis/analysis-forest-plot';
import { previewAnalysis } from '../../core/api/fn/analysis/preview-analysis';
import { runAnalysis } from '../../core/api/fn/analysis/run-analysis';
import { getAnalysisPlan } from '../../core/api/fn/protocol/get-analysis-plan';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { AssemblyOut } from '../../core/api/models/assembly-out';
import { OutcomeOut } from '../../core/api/models/outcome-out';
import { PlanOut } from '../../core/api/models/plan-out';
import { RunOut } from '../../core/api/models/run-out';
import { withJsonBody } from '../../core/errors/problem';
import { fileNameFrom, saveFile } from '../../shared/download';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { favoured, formatNumber, formatP, heterogeneity, shown } from './meta-reading';

type Measure = 'MD' | 'SMD' | 'OR' | 'RR' | 'RD';
type Method = 'REML' | 'DL' | 'PM' | 'FE';

/**
 * Meta-analysis wizard (docs/modulos.md 7.7): 1 outcome and studies, 2 effect measure,
 * 3 direction, 4 model, 5 result in plain language with the forest plot. Every number
 * comes from the R service; the screen only shows and explains it.
 */
@Component({
  selector: 'rm-meta-analysis-page',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatExpansionModule,
    MatFormFieldModule,
    MatSelectModule,
    MatStepperModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <p class="muted">
      {{ 'meta.intro' | transloco }}
      <span class="term" tabindex="0" [matTooltip]="'glossary.metaAnalysis' | transloco">?</span>
    </p>
    @if (plan(); as pl) {
      @if (!pl.defined) {
        <p class="notice">
          {{ 'meta.noPlan' | transloco }}
          <a [routerLink]="['/projetos', projectId(), 'protocolo']">{{
            'meta.goToPlan' | transloco
          }}</a>
        </p>
      }
    }
    <rm-form-error [error]="error()" />

    <mat-stepper [linear]="false" #stepper orientation="vertical">
      <!-- 1. Outcome, time point and studies -->
      <mat-step [label]="'meta.step1.title' | transloco">
        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'meta.step1.outcome' | transloco }}</mat-label>
            <mat-select [(ngModel)]="outcomeId" (ngModelChange)="onOutcome()">
              @for (o of outcomes(); track o.id) {
                <mat-option [value]="o.id">{{ o.name }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'meta.step1.timepoint' | transloco }}</mat-label>
            <mat-select [(ngModel)]="timepoint" (ngModelChange)="preview()">
              @for (t of timepoints(); track t) {
                <mat-option [value]="t">{{ t }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          @if (plan()?.adjusted === 'separate') {
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>
                {{ 'meta.step1.dataSet' | transloco }}
              </mat-label>
              <mat-select [(ngModel)]="dataSet" (ngModelChange)="preview()">
                <mat-option value="unadjusted">{{
                  'meta.dataSet.unadjusted' | transloco
                }}</mat-option>
                <mat-option value="adjusted">{{ 'meta.dataSet.adjusted' | transloco }}</mat-option>
              </mat-select>
            </mat-form-field>
            <span class="term" tabindex="0" [matTooltip]="'glossary.adjusted' | transloco">?</span>
          }
        </div>
        @if (assembly(); as a) {
          <p>
            <strong>{{
              'meta.step1.included' | transloco: { k: a.k, total: a.studies.length }
            }}</strong>
          </p>
          <ul class="item-list">
            @for (s of a.studies; track s.study_id) {
              <li>
                <div>
                  <span [class]="s.included ? 'badge' : 'badge badge-block'">
                    {{ (s.included ? 'meta.step1.in' : 'meta.step1.out') | transloco }}
                  </span>
                  <strong> {{ s.label }}</strong>
                  @for (r of s.reasons; track r) {
                    <div class="muted">{{ 'meta.reason.' + r | transloco }}</div>
                  }
                  @for (f of s.flags; track f) {
                    <span class="badge" [matTooltip]="'meta.flagHelp.' + f | transloco">{{
                      'meta.flag.' + f | transloco
                    }}</span>
                  }
                </div>
              </li>
            }
          </ul>
          @for (b of a.blocks; track b) {
            <p class="notice notice-error" role="alert">{{ 'meta.block.' + b | transloco }}</p>
          }
        }
        <div class="actions">
          <button
            mat-flat-button
            matStepperNext
            type="button"
            [disabled]="!assembly() || !!assembly()?.blocks?.length"
          >
            {{ 'meta.next' | transloco }}
          </button>
        </div>
      </mat-step>

      <!-- 2. Effect measure -->
      <mat-step [label]="'meta.step2.title' | transloco">
        @if (assembly(); as a) {
          <p>
            {{
              'meta.step2.recommended'
                | transloco: { measure: ('meta.measure.' + a.measure | transloco) }
            }}
            {{ 'meta.measureReason.' + a.measure_reason | transloco }}
          </p>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'meta.step2.measure' | transloco }}</mat-label>
            <mat-select [(ngModel)]="measure" (ngModelChange)="preview()">
              <mat-option [value]="null">{{ 'meta.step2.auto' | transloco }}</mat-option>
              @for (m of measures(); track m) {
                <mat-option [value]="m">{{ 'meta.measure.' + m | transloco }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <p class="muted">{{ 'meta.measureHelp.' + a.measure | transloco }}</p>
          @for (b of a.blocks; track b) {
            <p class="notice notice-error" role="alert">{{ 'meta.block.' + b | transloco }}</p>
          }
        }
        <div class="actions">
          <button mat-button matStepperPrevious type="button">{{ 'meta.back' | transloco }}</button>
          <button
            mat-flat-button
            matStepperNext
            type="button"
            [disabled]="!!assembly()?.blocks?.length"
          >
            {{ 'meta.next' | transloco }}
          </button>
        </div>
      </mat-step>

      <!-- 3. Direction -->
      <mat-step [label]="'meta.step3.title' | transloco">
        @if (assembly(); as a) {
          <p>{{ 'meta.step3.intro' | transloco }}</p>
          <ul class="item-list">
            @for (s of includedStudies(); track s.study_id) {
              <li>
                <div>
                  <strong>{{ s.label }}</strong>
                  <span class="muted">
                    · {{ s.scale_name || ('meta.step3.noScale' | transloco) }} ·
                    {{
                      (s.higher_is_better === false
                        ? 'meta.step3.higherWorse'
                        : 'meta.step3.higherBetter'
                      ) | transloco
                    }}
                  </span>
                  @if (s.inverted) {
                    <span class="badge">{{ 'meta.step3.inverted' | transloco }}</span>
                  }
                </div>
              </li>
            }
          </ul>
        }
        <div class="actions">
          <button mat-button matStepperPrevious type="button">{{ 'meta.back' | transloco }}</button>
          <button mat-flat-button matStepperNext type="button">
            {{ 'meta.next' | transloco }}
          </button>
        </div>
      </mat-step>

      <!-- 4. Model -->
      <mat-step [label]="'meta.step4.title' | transloco">
        <p class="muted">{{ 'meta.step4.intro' | transloco }}</p>
        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'plan.model.method' | transloco }}</mat-label>
            <mat-select [(ngModel)]="method">
              @for (m of methods; track m) {
                <mat-option [value]="m">{{ 'plan.model.methods.' + m | transloco }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          @if (method !== 'FE') {
            <mat-checkbox [(ngModel)]="knha">{{ 'plan.model.knha' | transloco }}</mat-checkbox>
            <span class="term" tabindex="0" [matTooltip]="'glossary.hartungKnapp' | transloco"
              >?</span
            >
          }
        </div>
        <p class="muted">{{ 'meta.methodHelp.' + method | transloco }}</p>
        <div class="actions">
          <button mat-button matStepperPrevious type="button">{{ 'meta.back' | transloco }}</button>
          <button mat-flat-button matStepperNext type="button" [disabled]="busy()" (click)="run()">
            {{ 'meta.run' | transloco }}
          </button>
        </div>
      </mat-step>

      <!-- 5. Result -->
      <mat-step [label]="'meta.step5.title' | transloco">
        @if (result(); as r) {
          @if (r.not_planned.length) {
            <p class="notice notice-warn" role="status">
              {{ 'meta.notPlanned' | transloco }}
              @for (n of r.not_planned; track n) {
                <span class="badge">{{ 'meta.notPlannedItem.' + n | transloco }}</span>
              }
            </p>
          }
          <mat-card class="block">
            <mat-card-content>
              <p class="lead">{{ summary() }}</p>
              <p>{{ heterogeneityText() }}</p>
              <p class="muted">{{ predictionText() }}</p>
            </mat-card-content>
          </mat-card>

          <table class="result-table">
            <tbody>
              <tr>
                <th scope="row">
                  {{ 'meta.res.effect' | transloco: { measure: r.assembly.measure } }}
                </th>
                <td>{{ effectText() }}</td>
              </tr>
              <tr>
                <th scope="row">{{ 'meta.res.p' | transloco }}</th>
                <td>{{ fmtP(pooled()['p_value']) }}</td>
              </tr>
              <tr>
                <th scope="row">
                  {{ 'meta.res.pi' | transloco }}
                  <span
                    class="term"
                    tabindex="0"
                    [matTooltip]="'glossary.predictionInterval' | transloco"
                    >?</span
                  >
                </th>
                <td>{{ piText() }}</td>
              </tr>
              <tr>
                <th scope="row">
                  I²
                  <span class="term" tabindex="0" [matTooltip]="'glossary.i2' | transloco">?</span>
                </th>
                <td>{{ fmt(het()['i2'], 1) }}%</td>
              </tr>
              <tr>
                <th scope="row">
                  τ²
                  <span class="term" tabindex="0" [matTooltip]="'glossary.tau2' | transloco"
                    >?</span
                  >
                </th>
                <td>{{ fmt(het()['tau2'], 4) }}</td>
              </tr>
              <tr>
                <th scope="row">Q</th>
                <td>
                  {{ fmt(het()['q'], 2) }} ({{ 'meta.res.df' | transloco }} = {{ het()['q_df'] }}; p
                  = {{ fmtP(het()['q_p']) }})
                </td>
              </tr>
              <tr>
                <th scope="row">{{ 'meta.res.model' | transloco }}</th>
                <td>
                  {{ 'plan.model.methods.' + r.method | transloco }}
                  @if (r.test === 'knha') {
                    · Hartung-Knapp
                  }
                  · k = {{ r.result['k'] }}
                </td>
              </tr>
            </tbody>
          </table>

          @for (w of r.warnings; track w) {
            <div class="alert-item">{{ warningText(w) }}</div>
          }

          <h3>{{ 'meta.forest.title' | transloco }}</h3>
          <div class="row">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'rob.plots.lang' | transloco }}</mat-label>
              <mat-select [(ngModel)]="outputLang" (ngModelChange)="drawForest()">
                <mat-option value="pt-BR">Português</mat-option>
                <mat-option value="en">English</mat-option>
              </mat-select>
            </mat-form-field>
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="download('svg')">
              {{ 'rob.plots.downloadSvg' | transloco }}
            </button>
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="download('png')">
              {{ 'rob.plots.downloadPng' | transloco }}
            </button>
          </div>
          @if (forestUrl(); as url) {
            <img class="rob-plot" [src]="url" [alt]="'meta.forest.title' | transloco" />
          }

          <mat-accordion>
            <mat-expansion-panel>
              <mat-expansion-panel-header>
                <mat-panel-title>{{ 'meta.howToRead.title' | transloco }}</mat-panel-title>
              </mat-expansion-panel-header>
              <ul>
                @for (item of howToRead; track item) {
                  <li>{{ 'meta.howToRead.' + item | transloco }}</li>
                }
              </ul>
            </mat-expansion-panel>
          </mat-accordion>

          <p class="muted small">
            {{
              'meta.res.versions'
                | transloco: { r: r.r_meta['r_version'], metafor: r.r_meta['packages']['metafor'] }
            }}
          </p>
        } @else {
          <p class="muted">{{ 'meta.step5.empty' | transloco }}</p>
        }
        <div class="actions">
          <button mat-button matStepperPrevious type="button">{{ 'meta.back' | transloco }}</button>
        </div>
      </mat-step>
    </mat-stepper>
  `,
})
export class MetaAnalysisPage implements OnInit, OnDestroy {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: 'pt-BR' });

  protected readonly projectId = computed(() => this.context.project()!.id);
  protected readonly outcomes = signal<OutcomeOut[]>([]);
  protected readonly plan = signal<PlanOut | null>(null);
  protected readonly assembly = signal<AssemblyOut | null>(null);
  protected readonly result = signal<RunOut | null>(null);
  protected readonly forestUrl = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly methods: Method[] = ['REML', 'DL', 'PM', 'FE'];
  protected readonly howToRead = [
    'square',
    'line',
    'null',
    'diamond',
    'prediction',
    'weights',
    'marks',
  ];

  protected outcomeId: string | null = null;
  protected timepoint: string | null = null;
  protected dataSet: 'unadjusted' | 'adjusted' = 'unadjusted';
  protected measure: Measure | null = null;
  protected method: Method = 'REML';
  protected knha = true;
  protected outputLang: 'pt-BR' | 'en' = 'pt-BR';

  protected readonly includedStudies = computed(() =>
    (this.assembly()?.studies ?? []).filter((s) => s.included),
  );
  protected readonly pooled = computed(
    () => (this.result()?.result['pooled'] ?? {}) as Record<string, number>,
  );
  protected readonly het = computed(
    () => (this.result()?.result['heterogeneity'] ?? {}) as Record<string, number>,
  );

  async ngOnInit(): Promise<void> {
    const project_id = this.projectId();
    this.outputLang = this.lang().startsWith('en') ? 'en' : 'pt-BR';
    try {
      const [outcomes, plan] = await Promise.all([
        this.api.invoke(listOutcomes, { project_id }),
        this.api.invoke(getAnalysisPlan, { project_id }),
      ]);
      this.outcomes.set(outcomes);
      this.plan.set(plan);
      this.method = plan.model?.method ?? 'REML';
      this.knha = (plan.model?.test ?? 'knha') === 'knha';
      this.dataSet = plan.adjusted === 'adjusted_only' ? 'adjusted' : 'unadjusted';
      const first = plan.outcomes?.[0];
      if (first) {
        this.outcomeId = first.outcome_id;
        this.timepoint = first.timepoint ?? null;
      } else if (outcomes.length) {
        this.outcomeId = outcomes[0].id;
      }
      if (this.outcomeId && !this.timepoint) this.timepoint = this.timepoints()[0] ?? null;
      await this.preview();
    } catch (error) {
      this.error.set(error);
    }
  }

  ngOnDestroy(): void {
    this.clearForest();
  }

  protected timepoints(): string[] {
    return this.outcomes().find((o) => o.id === this.outcomeId)?.timepoints ?? [];
  }

  protected measures(): Measure[] {
    const type = this.outcomes().find((o) => o.id === this.outcomeId)?.type;
    return type === 'dichotomous' ? ['RR', 'OR', 'RD'] : ['MD', 'SMD'];
  }

  protected onOutcome(): void {
    this.timepoint = this.timepoints()[0] ?? null;
    this.measure = null;
    void this.preview();
  }

  private body() {
    return {
      outcome_id: this.outcomeId!,
      timepoint: this.timepoint!,
      measure: this.measure,
      data_set: this.dataSet,
    };
  }

  async preview(): Promise<void> {
    this.result.set(null);
    this.clearForest();
    if (!this.outcomeId || !this.timepoint) return;
    await this.guard(async () => {
      this.assembly.set(
        await this.api.invoke(previewAnalysis, { project_id: this.projectId(), body: this.body() }),
      );
    });
  }

  async run(): Promise<void> {
    if (!this.outcomeId || !this.timepoint) return;
    await this.guard(async () => {
      const result = await this.api.invoke(runAnalysis, {
        project_id: this.projectId(),
        body: {
          ...this.body(),
          method: this.method,
          test: this.method === 'FE' || !this.knha ? 'z' : 'knha',
        },
      });
      this.result.set(result);
      this.assembly.set(result.assembly);
    });
    await this.drawForest();
  }

  private forestBody(format: 'svg' | 'png') {
    return {
      ...this.body(),
      method: this.method,
      test: (this.method === 'FE' || !this.knha ? 'z' : 'knha') as 'z' | 'knha',
      format,
      lang: this.outputLang,
    };
  }

  private clearForest(): void {
    const url = this.forestUrl();
    if (url) URL.revokeObjectURL(url);
    this.forestUrl.set(null);
  }

  async drawForest(): Promise<void> {
    if (!this.result()) return;
    await this.guard(async () => {
      const response = await this.api.invoke$Response(analysisForestPlot, {
        project_id: this.projectId(),
        body: this.forestBody('svg'),
      });
      this.clearForest();
      this.forestUrl.set(URL.createObjectURL(response.body));
    });
  }

  async download(format: 'svg' | 'png'): Promise<void> {
    await this.guard(async () => {
      const response = await this.api.invoke$Response(analysisForestPlot, {
        project_id: this.projectId(),
        body: this.forestBody(format),
      });
      saveFile(
        response.body,
        fileNameFrom(response.headers.get('content-disposition'), `forest.${format}`),
      );
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
    }
  }

  // ---- Reading the result (numbers from R, words from the translations) -----------

  private t(key: string, params?: Record<string, unknown>): string {
    this.lang();
    return this.transloco.translate(key, params);
  }

  protected fmt(value: number | undefined, digits = 2): string {
    return formatNumber(value, this.lang(), digits);
  }

  protected fmtP(value: number | undefined): string {
    return formatP(value, this.lang());
  }

  private onScale(value: number | undefined): string {
    const r = this.result();
    if (!r || value === undefined) return '—';
    return this.fmt(shown(value, r.assembly.measure));
  }

  protected effectText(): string {
    const p = this.pooled();
    return `${this.onScale(p['estimate'])} (${this.t('meta.res.ci')} ${this.onScale(p['ci_lb'])} ${this.t('meta.res.to')} ${this.onScale(p['ci_ub'])})`;
  }

  protected piText(): string {
    const p = this.pooled();
    return `${this.onScale(p['pi_lb'])} ${this.t('meta.res.to')} ${this.onScale(p['pi_ub'])}`;
  }

  private groupName(group: 'group1' | 'group2'): string {
    const r = this.result();
    const label = group === 'group1' ? r?.group1_label : r?.group2_label;
    return label ?? this.t('meta.' + group);
  }

  protected summary(): string {
    const r = this.result();
    if (!r) return '';
    const p = this.pooled();
    const side = favoured(p['ci_lb'], p['ci_ub'], r.favours_right);
    const params = {
      k: r.result['k'],
      outcome: r.assembly.outcome_name,
      timepoint: r.assembly.timepoint,
      group1: this.groupName('group1'),
      group2: this.groupName('group2'),
      favoured: side === 'none' ? '' : this.groupName(side),
      measure: r.assembly.measure,
      effect: this.effectText(),
    };
    return this.t(side === 'none' ? 'meta.summary.none' : 'meta.summary.favours', params);
  }

  protected heterogeneityText(): string {
    const i2 = this.het()['i2'];
    if (i2 === undefined) return '';
    return this.t('meta.summary.heterogeneity', {
      level: this.t('meta.heterogeneity.' + heterogeneity(i2)),
      i2: this.fmt(i2, 1),
    });
  }

  protected predictionText(): string {
    const r = this.result();
    if (!r || r.method === 'FE') return '';
    const p = this.pooled();
    return this.t('meta.summary.prediction', {
      lb: this.onScale(p['pi_lb']),
      ub: this.onScale(p['pi_ub']),
    });
  }

  protected warningText(code: string): string {
    const key = 'meta.warning.' + code;
    const text = this.t(key);
    return text === key ? code : text;
  }
}
