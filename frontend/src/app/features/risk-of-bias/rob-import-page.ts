import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { listRobTools } from '../../core/api/fn/risk-of-bias/list-rob-tools';
import { previewRobImport } from '../../core/api/fn/risk-of-bias/preview-rob-import';
import { runRobImport } from '../../core/api/fn/risk-of-bias/run-rob-import';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { ImportReport } from '../../core/api/models/import-report';
import { OutcomeOut } from '../../core/api/models/outcome-out';
import { RobPreview } from '../../core/api/models/rob-preview';
import { TargetColumn } from '../../core/api/models/target-column';
import { ToolOut } from '../../core/api/models/tool-out';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { localized } from './rob-tool-editor';

const FIXED = ['study', 'overall', 'overall_justification'];

/**
 * Migration of a project under way: the group's consolidated risk-of-bias table
 * (robvis format or any CSV/XLSX) becomes assessments marked as imported.
 */
@Component({
  selector: 'rm-rob-import-page',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatSelectModule,
    MatTableModule,
    FormError,
  ],
  template: `
    <a [routerLink]="['/projetos', projectId(), 'risco-de-vies']"
      >← {{ 'rob.table.back' | transloco }}</a
    >
    <h2>{{ 'rob.import.title' | transloco }}</h2>
    <p class="muted">{{ 'rob.import.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />

    <mat-card class="block">
      <mat-card-header>
        <mat-card-title
          ><h3>1. {{ 'rob.import.step.file' | transloco }}</h3></mat-card-title
        >
      </mat-card-header>
      <mat-card-content>
        <div class="row">
          <mat-form-field subscriptSizing="dynamic" class="wide">
            <mat-label>{{ 'rob.table.tool' | transloco }}</mat-label>
            <mat-select [(ngModel)]="toolId" (ngModelChange)="reset()">
              @for (t of tools(); track t.id) {
                <mat-option [value]="t.id">{{ name(t) }} ({{ t.template_version }})</mat-option>
              }
            </mat-select>
          </mat-form-field>
          @if (needsTarget()) {
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'rob.study.outcome' | transloco }}</mat-label>
              <mat-select
                [(ngModel)]="outcomeId"
                (ngModelChange)="timepoint = null; report.set(null)"
              >
                @for (o of outcomes(); track o.id) {
                  <mat-option [value]="o.id">{{ o.name }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'rob.study.timepoint' | transloco }}</mat-label>
              <mat-select [(ngModel)]="timepoint" (ngModelChange)="report.set(null)">
                @for (t of timepoints(); track t) {
                  <mat-option [value]="t">{{ t }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
          }
        </div>
        @if (toolId) {
          <label class="file-input">
            <span class="sr-only">{{ 'rob.import.step.file' | transloco }}</span>
            <input type="file" accept=".csv,.xlsx,.txt" (change)="choose($event)" />
          </label>
        }
        @if (preview(); as p) {
          <p>{{ 'import.rowsFound' | transloco: { count: p.row_count } }}</p>
        }
      </mat-card-content>
    </mat-card>

    @if (preview(); as p) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>2. {{ 'import.step.mapping' | transloco }}</h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <p class="muted">{{ 'rob.import.mappingHint' | transloco }}</p>
          <div class="mapping-grid">
            @for (target of p.targets; track target.key) {
              <mat-form-field>
                <mat-label>{{ targetLabel(target) }}{{ target.required ? ' *' : '' }}</mat-label>
                <mat-select [(ngModel)]="mapping[target.key]" (ngModelChange)="report.set(null)">
                  <mat-option [value]="null">{{ 'import.notInFile' | transloco }}</mat-option>
                  @for (column of p.columns; track column) {
                    <mat-option [value]="column">{{ column }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            }
          </div>
          <h4>{{ 'import.sample' | transloco }}</h4>
          <div class="table-scroll">
            <table class="sample">
              <thead>
                <tr>
                  @for (column of p.columns; track column) {
                    <th>{{ column }}</th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of p.sample; track $index) {
                  <tr>
                    @for (cell of row; track $index) {
                      <td>{{ cell }}</td>
                    }
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="actions">
            <button
              mat-flat-button
              type="button"
              [disabled]="!ready() || busy()"
              (click)="send(true)"
            >
              {{ 'import.check' | transloco }}
            </button>
          </div>
        </mat-card-content>
      </mat-card>
    }

    @if (report(); as r) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>3. {{ 'import.step.review' | transloco }}</h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          @if (!r.dry_run) {
            <div class="notice notice-ok" role="status">
              {{ 'rob.import.done' | transloco: { created: r.created } }}
            </div>
          } @else {
            <p>{{ 'import.summary' | transloco: { valid: r.valid_rows, total: r.total_rows } }}</p>
          }
          @if (r.errors.length) {
            <div class="notice notice-warn" role="status">
              {{ 'import.errorsIntro' | transloco: { count: r.errors.length } }}
            </div>
            <table mat-table [dataSource]="r.errors" class="full-table">
              <ng-container matColumnDef="row">
                <th mat-header-cell *matHeaderCellDef>{{ 'import.row' | transloco }}</th>
                <td mat-cell *matCellDef="let e">{{ e.row }}</td>
              </ng-container>
              <ng-container matColumnDef="field">
                <th mat-header-cell *matHeaderCellDef>{{ 'import.field' | transloco }}</th>
                <td mat-cell *matCellDef="let e">{{ fieldLabel(e.field) }}</td>
              </ng-container>
              <ng-container matColumnDef="problem">
                <th mat-header-cell *matHeaderCellDef>{{ 'import.problem' | transloco }}</th>
                <td mat-cell *matCellDef="let e">{{ 'importErrors.' + e.code | transloco }}</td>
              </ng-container>
              <tr mat-header-row *matHeaderRowDef="errorColumns"></tr>
              <tr mat-row *matRowDef="let row; columns: errorColumns"></tr>
            </table>
          }
          <div class="actions">
            @if (r.dry_run && r.valid_rows > 0) {
              <button mat-flat-button type="button" [disabled]="busy()" (click)="send(false)">
                {{ 'import.confirm' | transloco: { count: r.valid_rows } }}
              </button>
            }
            @if (!r.dry_run) {
              <a
                mat-flat-button
                [routerLink]="['/projetos', projectId(), 'risco-de-vies', 'tabela']"
              >
                {{ 'rob.table.open' | transloco }}
              </a>
            }
          </div>
        </mat-card-content>
      </mat-card>
    }
  `,
})
export class RobImportPage implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: 'pt-BR' });

  protected readonly projectId = computed(() => this.context.project()!.id);
  protected readonly errorColumns = ['row', 'field', 'problem'];
  protected readonly tools = signal<ToolOut[]>([]);
  protected readonly outcomes = signal<OutcomeOut[]>([]);
  protected readonly preview = signal<RobPreview | null>(null);
  protected readonly report = signal<ImportReport | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  private readonly selectedTool = signal<string | null>(null);
  protected toolId: string | null = null;
  protected outcomeId: string | null = null;
  protected timepoint: string | null = null;
  protected mapping: Record<string, string | null> = {};
  private file: File | null = null;

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
    try {
      const [tools, outcomes] = await Promise.all([
        this.api.invoke(listRobTools, { project_id }),
        this.api.invoke(listOutcomes, { project_id }),
      ]);
      this.tools.set(tools);
      this.outcomes.set(outcomes);
    } catch (error) {
      this.error.set(error);
    }
  }

  protected name(tool: ToolOut): string {
    return localized(tool.structure['name'] as Record<string, string>, this.lang());
  }

  protected timepoints(): string[] {
    return this.outcomes().find((o) => o.id === this.outcomeId)?.timepoints ?? [];
  }

  protected targetLabel(target: TargetColumn): string {
    this.lang();
    if (FIXED.includes(target.key)) {
      return this.transloco.translate('rob.import.fields.' + target.key);
    }
    return `${target.short} · ${localized(target.name, this.lang())}`;
  }

  protected fieldLabel(key: string | null | undefined): string {
    if (!key) return '';
    const target = this.preview()?.targets.find((t) => t.key === key);
    return target ? this.targetLabel(target) : key;
  }

  protected ready(): boolean {
    const p = this.preview();
    if (!p) return false;
    if (this.needsTarget() && (!this.outcomeId || !this.timepoint)) return false;
    return p.targets.every((t) => !t.required || !!this.mapping[t.key]);
  }

  protected reset(): void {
    this.selectedTool.set(this.toolId);
    this.preview.set(null);
    this.report.set(null);
    this.outcomeId = null;
    this.timepoint = null;
    this.file = null;
  }

  async choose(event: Event): Promise<void> {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file || !this.toolId) return;
    this.file = file;
    this.preview.set(null);
    this.report.set(null);
    const toolId = this.toolId;
    await this.run(async () => {
      const preview = await this.api.invoke(previewRobImport, {
        project_id: this.projectId(),
        body: { tool_id: toolId, file: file as unknown as string },
      });
      this.mapping = { ...preview.suggested_mapping };
      this.preview.set(preview);
    });
  }

  async send(dryRun: boolean): Promise<void> {
    if (!this.file || !this.toolId) return;
    const file = this.file;
    const toolId = this.toolId;
    const mapping = Object.fromEntries(
      Object.entries(this.mapping).filter((entry): entry is [string, string] => !!entry[1]),
    );
    await this.run(async () => {
      this.report.set(
        await this.api.invoke(runRobImport, {
          project_id: this.projectId(),
          body: {
            tool_id: toolId,
            file: file as unknown as string,
            mapping: JSON.stringify(mapping),
            outcome_id: this.needsTarget() ? this.outcomeId : null,
            timepoint: this.needsTarget() ? this.timepoint : null,
            dry_run: dryRun,
          },
        }),
      );
    });
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
