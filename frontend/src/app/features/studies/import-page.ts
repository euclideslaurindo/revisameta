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
import { previewImport } from '../../core/api/fn/studies/preview-import';
import { runImport } from '../../core/api/fn/studies/run-import';
import { ImportReport } from '../../core/api/models/import-report';
import { Preview } from '../../core/api/models/preview';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

const FIELDS = ['label', 'title', 'authors', 'year', 'doi', 'pmid', 'journal', 'design', 'notes'] as const;
type Field = (typeof FIELDS)[number];

@Component({
  selector: 'rm-import-page',
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
    <h2>{{ 'import.title' | transloco }}</h2>
    <p class="muted">{{ 'import.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />

    <mat-card class="block">
      <mat-card-header><mat-card-title><h3>1. {{ 'import.step.file' | transloco }}</h3></mat-card-title></mat-card-header>
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
        <mat-card-header><mat-card-title><h3>2. {{ 'import.step.mapping' | transloco }}</h3></mat-card-title></mat-card-header>
        <mat-card-content>
          <p class="muted">{{ 'import.mappingHint' | transloco }}</p>
          <div class="mapping-grid">
            @for (field of fields; track field) {
              <mat-form-field>
                <mat-label>
                  {{ 'import.fields.' + field | transloco }}{{ field === 'title' ? ' *' : '' }}
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
              <thead><tr>@for (column of p.columns; track column) { <th>{{ column }}</th> }</tr></thead>
              <tbody>
                @for (row of p.sample; track $index) {
                  <tr>@for (cell of row; track $index) { <td>{{ cell }}</td> }</tr>
                }
              </tbody>
            </table>
          </div>
          <div class="actions">
            <button mat-flat-button type="button" [disabled]="!mapping.title || busy()" (click)="check()">
              {{ 'import.check' | transloco }}
            </button>
          </div>
        </mat-card-content>
      </mat-card>
    }

    @if (report(); as r) {
      <mat-card class="block">
        <mat-card-header><mat-card-title><h3>3. {{ 'import.step.review' | transloco }}</h3></mat-card-title></mat-card-header>
        <mat-card-content>
          @if (!r.dry_run) {
            <div class="notice notice-ok" role="status">{{ 'import.done' | transloco: { created: r.created } }}</div>
          } @else {
            <p>{{ 'import.summary' | transloco: { valid: r.valid_rows, total: r.total_rows } }}</p>
          }
          @if (r.errors.length) {
            <div class="notice notice-warn" role="status">{{ 'import.errorsIntro' | transloco: { count: r.errors.length } }}</div>
            <table mat-table [dataSource]="r.errors" class="full-table">
              <ng-container matColumnDef="row">
                <th mat-header-cell *matHeaderCellDef>{{ 'import.row' | transloco }}</th>
                <td mat-cell *matCellDef="let e">{{ e.row }}</td>
              </ng-container>
              <ng-container matColumnDef="field">
                <th mat-header-cell *matHeaderCellDef>{{ 'import.field' | transloco }}</th>
                <td mat-cell *matCellDef="let e">{{ e.field ? ('import.fields.' + e.field | transloco) : '' }}</td>
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
              <button mat-flat-button type="button" [disabled]="busy()" (click)="confirmImport()">
                {{ 'import.confirm' | transloco: { count: r.valid_rows } }}
              </button>
            }
            @if (!r.dry_run) {
              <a mat-flat-button routerLink="..">{{ 'import.seeStudies' | transloco }}</a>
            }
          </div>
        </mat-card-content>
      </mat-card>
    }
  `,
})
export class ImportPage {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly fields = FIELDS;
  protected readonly errorColumns = ['row', 'field', 'problem'];
  protected readonly preview = signal<Preview | null>(null);
  protected readonly report = signal<ImportReport | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected mapping: Partial<Record<Field, string | null>> = {};
  private file: File | null = null;

  private projectId(): string {
    return this.context.project()!.id;
  }

  async choose(event: Event): Promise<void> {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.file = file;
    this.preview.set(null);
    this.report.set(null);
    await this.run(async () => {
      const preview = await this.api.invoke(previewImport, {
        project_id: this.projectId(),
        body: { file: file as unknown as string },
      });
      this.mapping = { ...preview.suggested_mapping } as Partial<Record<Field, string>>;
      this.preview.set(preview);
    });
  }

  private chosenMapping(): Record<string, string> {
    return Object.fromEntries(
      Object.entries(this.mapping).filter((entry): entry is [string, string] => !!entry[1]),
    );
  }

  private async send(dryRun: boolean): Promise<void> {
    if (!this.file) return;
    const file = this.file;
    await this.run(async () => {
      this.report.set(
        await this.api.invoke(runImport, {
          project_id: this.projectId(),
          body: {
            file: file as unknown as string,
            mapping: JSON.stringify(this.chosenMapping()),
            dry_run: dryRun,
          },
        }),
      );
    });
  }

  check(): Promise<void> {
    return this.send(true);
  }

  confirmImport(): Promise<void> {
    return this.send(false);
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
