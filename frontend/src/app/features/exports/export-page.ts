import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatRadioModule } from '@angular/material/radio';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { exportExtraction } from '../../core/api/fn/exports/export-extraction';
import { extractionExportStatus } from '../../core/api/fn/exports/extraction-export-status';
import { CsvStyle } from '../../core/api/models/csv-style';
import { ExportMode } from '../../core/api/models/export-mode';
import { ExportStatus } from '../../core/api/models/export-status';
import { FileFormat } from '../../core/api/models/file-format';
import { withJsonBody } from '../../core/errors/problem';
import { fileNameFrom, saveFile } from '../../shared/download';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { BackupCard } from './backup-card';
import { BibliographyCard } from './bibliography-card';

/**
 * Export of the extracted data. Never blank in silence (lesson L2): studies left
 * out are listed and must be acknowledged; the individual (pre-consensus)
 * extractions are the alternative for admins.
 */
@Component({
  selector: 'rm-export-page',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatRadioModule,
    FormError,
    BibliographyCard,
    BackupCard,
  ],
  template: `
    <p class="muted">{{ 'export.intro' | transloco }}</p>
    @if (status(); as s) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>{{ 'export.extraction.title' | transloco }}</h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <p>{{ 'export.extraction.ready' | transloco: { ready: s.ready, total: s.total } }}</p>
          @if (s.locked) {
            <p class="badge">{{ 'review.action.lock' | transloco }}</p>
          }
          @if (s.missing.length) {
            <div class="notice" role="status">
              <p>{{ 'export.extraction.missing' | transloco: { count: s.missing.length } }}</p>
              <ul>
                @for (m of s.missing; track m.study_id) {
                  <li>{{ m.label }} — {{ 'export.missing.' + m.reason | transloco }}</li>
                }
              </ul>
            </div>
          }

          <h4>{{ 'export.content' | transloco }}</h4>
          <mat-radio-group [(ngModel)]="mode" class="stack">
            <mat-radio-button value="consensus">{{
              'export.mode.consensus' | transloco
            }}</mat-radio-button>
            @if (s.individual_allowed) {
              <mat-radio-button value="individual">{{
                'export.mode.individual' | transloco
              }}</mat-radio-button>
            }
          </mat-radio-group>

          <h4>{{ 'export.format' | transloco }}</h4>
          <mat-radio-group [(ngModel)]="format" class="stack">
            <mat-radio-button value="xlsx">{{
              'export.formats.xlsx' | transloco
            }}</mat-radio-button>
            <mat-radio-button value="csv">{{ 'export.formats.csv' | transloco }}</mat-radio-button>
          </mat-radio-group>
          @if (format === 'csv') {
            <mat-radio-group [(ngModel)]="csvStyle" class="stack indent">
              <mat-radio-button value="excel">{{
                'export.csv.excel' | transloco
              }}</mat-radio-button>
              <mat-radio-button value="r">{{ 'export.csv.r' | transloco }}</mat-radio-button>
            </mat-radio-group>
          }

          <h4>{{ 'export.language' | transloco }}</h4>
          <mat-radio-group [(ngModel)]="lang" class="stack">
            <mat-radio-button value="pt-BR">{{ 'languages.pt-BR' | transloco }}</mat-radio-button>
            <mat-radio-button value="en">{{ 'languages.en' | transloco }}</mat-radio-button>
          </mat-radio-group>

          @if (s.missing.length) {
            <mat-checkbox [(ngModel)]="acknowledged">
              {{ 'export.acknowledge' | transloco: { count: s.missing.length } }}
            </mat-checkbox>
          }
          <rm-form-error [error]="error()" />
          <div class="actions">
            <button mat-flat-button type="button" [disabled]="busy()" (click)="download()">
              {{ 'export.download' | transloco }}
            </button>
          </div>
        </mat-card-content>
      </mat-card>
    }
    <rm-bibliography-card />
    <rm-backup-card />
  `,
})
export class ExportPage implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly status = signal<ExportStatus | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly projectId = computed(() => this.context.project()!.id);

  protected mode: ExportMode = 'consensus';
  protected format: FileFormat = 'xlsx';
  protected csvStyle: CsvStyle = 'excel';
  protected lang = 'pt-BR';
  protected acknowledged = false;

  async ngOnInit(): Promise<void> {
    this.lang = this.context.project()?.report_language ?? 'pt-BR';
    try {
      this.status.set(
        await this.api.invoke(extractionExportStatus, { project_id: this.projectId() }),
      );
    } catch (error) {
      this.error.set(error);
    }
  }

  async download(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const response = await this.api.invoke$Response(exportExtraction, {
        project_id: this.projectId(),
        file_format: this.format,
        mode: this.mode,
        csv_style: this.csvStyle,
        lang: this.lang,
        acknowledge_missing: this.acknowledged,
      });
      const name = fileNameFrom(
        response.headers.get('content-disposition'),
        `export.${this.format}`,
      );
      saveFile(response.body, name);
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }
}
