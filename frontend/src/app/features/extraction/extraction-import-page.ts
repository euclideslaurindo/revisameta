import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { listGroups } from '../../core/api/fn/protocol/list-groups';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { listStudies } from '../../core/api/fn/studies/list-studies';
import { previewExtractionImport } from '../../core/api/fn/extraction/preview-extraction-import';
import { runExtractionImport } from '../../core/api/fn/extraction/run-extraction-import';
import { ExtractionImportPreview } from '../../core/api/models/extraction-import-preview';
import { ExtractionImportReport } from '../../core/api/models/extraction-import-report';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

/** Columns of the spreadsheet, in the order they are shown. */
const FIELDS = [
  'study',
  'group',
  'outcome',
  'timepoint',
  'value_type',
  'group_n',
  'n',
  'mean',
  'sd',
  'se',
  'ci_low',
  'ci_high',
  'median',
  'q1',
  'q3',
  'min',
  'max',
  'events',
  'total',
  'source_location',
  'dispersion_source',
  'scale_name',
  'scale_min',
  'scale_max',
  'higher_is_better',
] as const;
type Field = (typeof FIELDS)[number];
const REQUIRED: readonly Field[] = ['study', 'group', 'outcome'];
type Kind = 'studies' | 'groups' | 'outcomes';

interface Option {
  id: string;
  name: string;
}

/**
 * Brings the numbers of an extraction spreadsheet the group already has. They become the
 * person's own draft extraction of each study, with every protection of the form.
 */
@Component({
  selector: 'rm-extraction-import-page',
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
    <a routerLink=".." class="back">← {{ 'project.nav.studies' | transloco }}</a>
    <h2>{{ 'extractionImport.title' | transloco }}</h2>
    <p class="muted">{{ 'extractionImport.intro' | transloco }}</p>
    <details class="block">
      <summary>{{ 'extractionImport.layoutTitle' | transloco }}</summary>
      <p>{{ 'extractionImport.layout' | transloco }}</p>
      <div class="table-scroll">
        <table class="sample">
          <thead>
            <tr>
              @for (h of exampleHeader; track h) {
                <th>{{ h }}</th>
              }
            </tr>
          </thead>
          <tbody>
            @for (row of exampleRows; track $index) {
              <tr>
                @for (cell of row; track $index) {
                  <td>{{ cell }}</td>
                }
              </tr>
            }
          </tbody>
        </table>
      </div>
      <p class="muted">{{ 'extractionImport.layoutNote' | transloco }}</p>
    </details>
    <rm-form-error [error]="error()" />

    <mat-card class="block">
      <mat-card-header
        ><mat-card-title
          ><h3>1. {{ 'import.step.file' | transloco }}</h3></mat-card-title
        ></mat-card-header
      >
      <mat-card-content>
        <label class="file-input">
          <span class="sr-only">{{ 'import.step.file' | transloco }}</span>
          <input type="file" accept=".csv,.xlsx,.txt" (change)="choose($event)" />
        </label>
        @if (preview(); as p) {
          <p>{{ 'import.rowsFound' | transloco: { count: p.row_count } }}</p>
        }
      </mat-card-content>
    </mat-card>

    @if (preview(); as p) {
      <mat-card class="block">
        <mat-card-header
          ><mat-card-title
            ><h3>2. {{ 'import.step.mapping' | transloco }}</h3></mat-card-title
          ></mat-card-header
        >
        <mat-card-content>
          <p class="muted">{{ 'extractionImport.mappingHint' | transloco }}</p>
          <div class="mapping-grid">
            @for (field of fields; track field) {
              <mat-form-field>
                <mat-label>
                  {{ 'extractionImport.fields.' + field | transloco
                  }}{{ required.includes(field) ? ' *' : '' }}
                </mat-label>
                <mat-select [(ngModel)]="mapping[field]" (ngModelChange)="report.set(null)">
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
        </mat-card-content>
      </mat-card>

      <mat-card class="block">
        <mat-card-header
          ><mat-card-title
            ><h3>3. {{ 'extractionImport.step.names' | transloco }}</h3></mat-card-title
          ></mat-card-header
        >
        <mat-card-content>
          <p class="muted">{{ 'extractionImport.namesHint' | transloco }}</p>
          @for (kind of kinds; track kind) {
            @if (p[kind].length) {
              <h4>{{ 'extractionImport.names.' + kind | transloco }}</h4>
              <div class="mapping-grid">
                @for (item of p[kind]; track item.text) {
                  <mat-form-field>
                    <mat-label>“{{ item.text }}” ({{ item.rows }})</mat-label>
                    <mat-select
                      [(ngModel)]="matches[kind][item.text]"
                      (ngModelChange)="report.set(null)"
                    >
                      <mat-option [value]="null">{{
                        'extractionImport.none.' + kind | transloco
                      }}</mat-option>
                      @for (o of options()[kind]; track o.id) {
                        <mat-option [value]="o.id">{{ o.name }}</mat-option>
                      }
                    </mat-select>
                  </mat-form-field>
                }
              </div>
            }
          }
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
        <mat-card-header
          ><mat-card-title
            ><h3>4. {{ 'import.step.review' | transloco }}</h3></mat-card-title
          ></mat-card-header
        >
        <mat-card-content>
          @if (!r.dry_run) {
            <div class="notice notice-ok" role="status">
              {{ 'extractionImport.done' | transloco: { rows: r.imported_rows } }}
            </div>
          } @else {
            <p>
              {{ 'import.summary' | transloco: { valid: r.valid_rows, total: r.total_rows } }}
            </p>
          }
          <ul class="item-list">
            @for (s of r.studies; track s.study_id) {
              <li>
                @if (s.extraction_id) {
                  <a [routerLink]="['..', s.study_id]">{{ s.label }}</a>
                } @else {
                  <span>{{ s.label }}</span>
                }
                <span class="badge" [class.badge-block]="s.status === 'skipped'">
                  {{ 'extractionImport.status.' + s.status | transloco: { rows: s.rows } }}
                </span>
                @if (s.code) {
                  <span class="muted">{{ 'importErrors.' + s.code | transloco }}</span>
                }
              </li>
            }
          </ul>
          @if (r.errors.length) {
            <div class="notice notice-warn" role="status">
              {{ 'extractionImport.errorsIntro' | transloco: { count: r.errors.length } }}
            </div>
            <table mat-table [dataSource]="r.errors" class="full-table">
              <ng-container matColumnDef="row">
                <th mat-header-cell *matHeaderCellDef>{{ 'import.row' | transloco }}</th>
                <td mat-cell *matCellDef="let e">{{ e.row }}</td>
              </ng-container>
              <ng-container matColumnDef="field">
                <th mat-header-cell *matHeaderCellDef>{{ 'import.field' | transloco }}</th>
                <td mat-cell *matCellDef="let e">
                  {{ e.field ? ('extractionImport.fields.' + e.field | transloco) : '' }}
                </td>
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
            @if (r.dry_run && readyStudies(r) > 0) {
              <button mat-flat-button type="button" [disabled]="busy()" (click)="send(false)">
                {{ 'extractionImport.confirm' | transloco: { count: readyStudies(r) } }}
              </button>
            }
          </div>
          @if (!r.dry_run && r.imported_rows > 0) {
            <p class="notice">{{ 'extractionImport.next' | transloco }}</p>
          }
        </mat-card-content>
      </mat-card>
    }
  `,
})
export class ExtractionImportPage {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly fields = FIELDS;
  protected readonly required = REQUIRED;
  protected readonly kinds: Kind[] = ['studies', 'groups', 'outcomes'];
  protected readonly errorColumns = ['row', 'field', 'problem'];
  /** A FICTITIOUS example of the layout (made-up study and numbers). */
  protected readonly exampleHeader = [
    'estudo',
    'grupo',
    'desfecho',
    'momento',
    'n',
    'media',
    'dp',
    'pagina',
  ];
  protected readonly exampleRows = [
    ['Exemplo 2020', '< 5 anos', 'QI', '5 anos', '20', '92,5', '10', 'Tabela 2'],
    ['Exemplo 2020', '≥ 5 anos', 'QI', '5 anos', '25', '85', '11', 'Tabela 2'],
  ];
  protected readonly preview = signal<ExtractionImportPreview | null>(null);
  protected readonly report = signal<ExtractionImportReport | null>(null);
  protected readonly options = signal<Record<Kind, Option[]>>({
    studies: [],
    groups: [],
    outcomes: [],
  });
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected mapping: Partial<Record<Field, string | null>> = {};
  protected matches: Record<Kind, Record<string, string | null>> = {
    studies: {},
    groups: {},
    outcomes: {},
  };
  protected ready(): boolean {
    return REQUIRED.every((f) => !!this.mapping[f]);
  }
  private file: File | null = null;

  private projectId(): string {
    return this.context.project()!.id;
  }

  protected readyStudies(r: ExtractionImportReport): number {
    return r.studies.filter((s) => s.status === 'ready').length;
  }

  async choose(event: Event): Promise<void> {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.file = file;
    this.preview.set(null);
    this.report.set(null);
    await this.run(async () => {
      const project_id = this.projectId();
      const [preview, studies, groups, outcomes] = await Promise.all([
        this.api.invoke(previewExtractionImport, {
          project_id,
          body: { file: file as unknown as string },
        }),
        this.api.invoke(listStudies, { project_id }),
        this.api.invoke(listGroups, { project_id }),
        this.api.invoke(listOutcomes, { project_id }),
      ]);
      this.options.set({
        studies: studies.map((s) => ({ id: s.id, name: s.label })),
        groups: groups.map((g) => ({ id: g.id, name: g.label })),
        outcomes: outcomes.map((o) => ({ id: o.id, name: o.name })),
      });
      this.mapping = { ...preview.suggested_mapping } as Partial<Record<Field, string>>;
      for (const kind of this.kinds) {
        this.matches[kind] = Object.fromEntries(
          preview[kind].map((m) => [m.text, m.match_id ?? null]),
        );
      }
      this.preview.set(preview);
    });
  }

  private chosenMapping(): Record<string, string> {
    return Object.fromEntries(
      Object.entries(this.mapping).filter((entry): entry is [string, string] => !!entry[1]),
    );
  }

  async send(dryRun: boolean): Promise<void> {
    if (!this.file) return;
    const file = this.file;
    await this.run(async () => {
      this.report.set(
        await this.api.invoke(runExtractionImport, {
          project_id: this.projectId(),
          body: {
            file: file as unknown as string,
            mapping: JSON.stringify(this.chosenMapping()),
            matches: JSON.stringify(this.matches),
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
