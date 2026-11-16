import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { listRobTools } from '../../core/api/fn/risk-of-bias/list-rob-tools';
import { robPlot } from '../../core/api/fn/risk-of-bias/rob-plot';
import { robTable } from '../../core/api/fn/risk-of-bias/rob-table';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { OutcomeOut } from '../../core/api/models/outcome-out';
import { TableOut } from '../../core/api/models/table-out';
import { ToolOut } from '../../core/api/models/tool-out';
import { withJsonBody } from '../../core/errors/problem';
import { fileNameFrom, saveFile } from '../../shared/download';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { localized } from './rob-tool-editor';

type PlotKind = 'traffic_light' | 'summary';

/** Screen colour of a level or answer (the plots use the robvis colours). */
export function cellClass(key: string | null | undefined): string {
  if (!key) return 'rob-level rob-level-empty';
  const stars = /^stars_(\d+)_of_(\d+)$/.exec(key);
  if (stars) {
    const [n, max] = [Number(stars[1]), Number(stars[2])];
    return 'rob-level rob-level-' + (n >= max ? 'low' : n === 0 ? 'high' : 'moderate');
  }
  const map: Record<string, string> = {
    Y: 'low',
    SY: 'low',
    good: 'low',
    PY: 'low_except_confounding',
    WY: 'low_except_confounding',
    U: 'moderate',
    fair: 'moderate',
    PN: 'some_concerns',
    WN: 'some_concerns',
    N: 'high',
    SN: 'high',
    poor: 'high',
    NI: 'no_information',
    NA: 'empty',
  };
  return 'rob-level rob-level-' + (map[key] ?? key);
}

/**
 * Consolidated risk of bias (studies x domains) and the robvis plots, built only from
 * submitted consensus assessments. Studies still being assessed are listed apart.
 */
@Component({
  selector: 'rm-rob-table-page',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <a [routerLink]="['/projetos', projectId(), 'risco-de-vies']"
      >← {{ 'rob.table.back' | transloco }}</a
    >
    <h2>{{ 'rob.table.title' | transloco }}</h2>
    <p class="muted">{{ 'rob.table.intro' | transloco }}</p>

    <div class="row">
      <mat-form-field subscriptSizing="dynamic" class="wide">
        <mat-label>{{ 'rob.table.tool' | transloco }}</mat-label>
        <mat-select [(ngModel)]="toolId" (ngModelChange)="onTool()">
          @for (t of tools(); track t.id) {
            <mat-option [value]="t.id">{{ name(t) }} ({{ t.template_version }})</mat-option>
          }
        </mat-select>
      </mat-form-field>
      @if (needsTarget()) {
        <mat-form-field subscriptSizing="dynamic">
          <mat-label>{{ 'rob.study.outcome' | transloco }}</mat-label>
          <mat-select [(ngModel)]="outcomeId" (ngModelChange)="timepoint = null; load()">
            @for (o of outcomes(); track o.id) {
              <mat-option [value]="o.id">{{ o.name }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field subscriptSizing="dynamic">
          <mat-label>{{ 'rob.study.timepoint' | transloco }}</mat-label>
          <mat-select [(ngModel)]="timepoint" (ngModelChange)="load()">
            @for (t of timepoints(); track t) {
              <mat-option [value]="t">{{ t }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
      }
    </div>
    <rm-form-error [error]="error()" />

    @if (data(); as d) {
      @if (d.pending.length) {
        <div class="notice notice-warn" role="status">
          <p>{{ 'rob.table.pending' | transloco: { count: d.pending.length } }}</p>
          <ul>
            @for (p of d.pending; track p.study_id) {
              <li>
                <a [routerLink]="['/projetos', projectId(), 'estudos', p.study_id]">{{
                  p.label
                }}</a>
                — {{ 'rob.table.reason.' + p.reason | transloco }}
              </li>
            }
          </ul>
        </div>
      }
      @if (d.rows.length === 0) {
        <p class="empty">{{ 'rob.table.empty' | transloco }}</p>
      } @else {
        <div class="table-scroll">
          <table class="rob-table">
            <thead>
              <tr>
                <th scope="col">{{ 'rob.table.study' | transloco }}</th>
                @for (c of d.columns; track c.key) {
                  <th scope="col" [matTooltip]="columnName(c.name)">{{ c.short }}</th>
                }
                <th scope="col">{{ 'rob.assessment.overall' | transloco }}</th>
              </tr>
            </thead>
            <tbody>
              @for (r of d.rows; track r.study_id) {
                <tr>
                  <th scope="row">
                    <a
                      [routerLink]="[
                        '/projetos',
                        projectId(),
                        'risco-de-vies',
                        'avaliacoes',
                        r.assessment_id,
                      ]"
                      >{{ r.label }}</a
                    >
                    @if (r.kind === 'imported') {
                      <span class="badge">{{ 'rob.table.imported' | transloco }}</span>
                    }
                  </th>
                  @for (c of d.columns; track c.key) {
                    <td>
                      <span [class]="cellClass(r.values[c.key])">{{ label(r.values[c.key]) }}</span>
                    </td>
                  }
                  <td>
                    <span [class]="cellClass(r.overall)">{{ label(r.overall) }}</span>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <ul class="muted legend-list">
          @for (c of d.columns; track c.key) {
            <li>{{ c.short }}: {{ columnName(c.name) }}</li>
          }
        </ul>

        <mat-card class="block">
          <mat-card-header>
            <mat-card-title
              ><h3>{{ 'rob.plots.title' | transloco }}</h3></mat-card-title
            >
          </mat-card-header>
          <mat-card-content>
            <p class="muted">{{ 'rob.plots.intro' | transloco }}</p>
            <div class="row">
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>{{ 'rob.plots.lang' | transloco }}</mat-label>
                <mat-select [(ngModel)]="outputLang" (ngModelChange)="clearPreview()">
                  <mat-option value="pt-BR">Português</mat-option>
                  <mat-option value="en">English</mat-option>
                </mat-select>
              </mat-form-field>
            </div>
            @if (d.pending.length) {
              <mat-checkbox [(ngModel)]="acknowledged">
                {{ 'rob.plots.acknowledge' | transloco: { count: d.pending.length } }}
              </mat-checkbox>
            }
            <div class="actions">
              @for (k of kinds; track k) {
                <button
                  mat-flat-button
                  type="button"
                  [disabled]="busy() || (d.pending.length > 0 && !acknowledged)"
                  (click)="preview(k)"
                >
                  {{ 'rob.plots.' + k | transloco }}
                </button>
              }
            </div>
            @if (previewUrl(); as url) {
              <img class="rob-plot" [src]="url" [alt]="'rob.plots.' + previewKind() | transloco" />
              <div class="actions">
                <button
                  mat-stroked-button
                  type="button"
                  [disabled]="busy()"
                  (click)="download('svg')"
                >
                  {{ 'rob.plots.downloadSvg' | transloco }}
                </button>
                <button
                  mat-stroked-button
                  type="button"
                  [disabled]="busy()"
                  (click)="download('png')"
                >
                  {{ 'rob.plots.downloadPng' | transloco }}
                </button>
              </div>
            }
          </mat-card-content>
        </mat-card>
      }
    }
  `,
})
export class RobTablePage implements OnInit, OnDestroy {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: 'pt-BR' });

  protected readonly projectId = computed(() => this.context.project()!.id);
  protected readonly tools = signal<ToolOut[]>([]);
  protected readonly outcomes = signal<OutcomeOut[]>([]);
  protected readonly data = signal<TableOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly previewUrl = signal<string | null>(null);
  protected readonly previewKind = signal<PlotKind>('traffic_light');
  protected readonly selectedTool = signal<string | null>(null);
  protected readonly kinds: PlotKind[] = ['traffic_light', 'summary'];
  protected readonly cellClass = cellClass;
  protected toolId: string | null = null;
  protected outcomeId: string | null = null;
  protected timepoint: string | null = null;
  protected outputLang: 'pt-BR' | 'en' = 'pt-BR';
  protected acknowledged = false;

  protected readonly needsTarget = computed(() => {
    const tool = this.tools().find((t) => t.id === this.selectedTool());
    if (!tool) return false;
    const s = tool.structure as {
      scope: string;
      judgement: { kind: string };
      domains: { questions: { level: string }[] }[];
    };
    return (
      s.scope === 'result' ||
      (s.judgement.kind === 'group_rule' &&
        s.domains.some((d) => d.questions.some((q) => q.level !== 'study')))
    );
  });

  async ngOnInit(): Promise<void> {
    const project_id = this.projectId();
    this.outputLang = this.lang().startsWith('en') ? 'en' : 'pt-BR';
    try {
      const [tools, outcomes] = await Promise.all([
        this.api.invoke(listRobTools, { project_id }),
        this.api.invoke(listOutcomes, { project_id }),
      ]);
      this.tools.set(tools);
      this.outcomes.set(outcomes);
      if (tools.length) {
        this.toolId = tools[0].id;
        this.onTool();
      }
    } catch (error) {
      this.error.set(error);
    }
  }

  ngOnDestroy(): void {
    this.clearPreview();
  }

  protected name(tool: ToolOut): string {
    return localized(tool.structure['name'] as Record<string, string>, this.lang());
  }

  protected columnName(name: Record<string, string>): string {
    return localized(name, this.lang());
  }

  protected timepoints(): string[] {
    return this.outcomes().find((o) => o.id === this.outcomeId)?.timepoints ?? [];
  }

  protected label(key: string | null | undefined): string {
    this.lang();
    if (!key) return '—';
    const stars = /^stars_(\d+)_of_(\d+)$/.exec(key);
    if (stars) return this.transloco.translate('rob.answer.stars', { n: stars[1] });
    for (const prefix of ['rob.judgement.', 'rob.answer.']) {
      const text = this.transloco.translate(prefix + key);
      if (text !== prefix + key) return text;
    }
    return key;
  }

  protected onTool(): void {
    this.selectedTool.set(this.toolId);
    this.outcomeId = null;
    this.timepoint = null;
    this.data.set(null);
    void this.load();
  }

  protected async load(): Promise<void> {
    this.clearPreview();
    this.acknowledged = false;
    if (!this.toolId) return;
    if (this.needsTarget() && (!this.outcomeId || !this.timepoint)) {
      this.data.set(null);
      return;
    }
    this.error.set(null);
    try {
      this.data.set(
        await this.api.invoke(robTable, {
          project_id: this.projectId(),
          tool_id: this.toolId,
          outcome_id: this.needsTarget() ? this.outcomeId : null,
          timepoint: this.needsTarget() ? this.timepoint : null,
        }),
      );
    } catch (error) {
      this.error.set(error);
    }
  }

  private async fetch(kind: PlotKind, format: 'svg' | 'png') {
    return this.api.invoke$Response(robPlot, {
      project_id: this.projectId(),
      body: {
        tool_id: this.toolId!,
        outcome_id: this.needsTarget() ? this.outcomeId : null,
        timepoint: this.needsTarget() ? this.timepoint : null,
        kind,
        format,
        lang: this.outputLang,
        acknowledge_missing: this.acknowledged,
      },
    });
  }

  protected clearPreview(): void {
    const url = this.previewUrl();
    if (url) URL.revokeObjectURL(url);
    this.previewUrl.set(null);
  }

  async preview(kind: PlotKind): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const response = await this.fetch(kind, 'svg');
      this.clearPreview();
      this.previewKind.set(kind);
      this.previewUrl.set(URL.createObjectURL(response.body));
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }

  async download(format: 'svg' | 'png'): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const response = await this.fetch(this.previewKind(), format);
      saveFile(
        response.body,
        fileNameFrom(response.headers.get('content-disposition'), `rob.${format}`),
      );
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }
}
