import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { bibliographyStatus } from '../../core/api/fn/exports/bibliography-status';
import { exportBibliography } from '../../core/api/fn/exports/export-bibliography';
import { BibFormat } from '../../core/api/models/bib-format';
import { BibStatus } from '../../core/api/models/bib-status';
import { withJsonBody } from '../../core/errors/problem';
import { fileNameFrom, saveFile } from '../../shared/download';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

/** Bibliography of the included studies: RIS, BibTeX or Vancouver text. */
@Component({
  selector: 'rm-bibliography-card',
  imports: [TranslocoPipe, MatButtonModule, MatCardModule, FormError],
  template: `
    <mat-card class="block">
      <mat-card-header>
        <mat-card-title
          ><h3>{{ 'export.bibliography.title' | transloco }}</h3></mat-card-title
        >
      </mat-card-header>
      <mat-card-content>
        <rm-form-error [error]="error()" />
        @if (status(); as s) {
          <p>{{ 'export.bibliography.records' | transloco: { n: s.records } }}</p>
          @if (s.incomplete.length) {
            <p class="warning" role="alert">
              {{
                'export.bibliography.incomplete' | transloco: { studies: s.incomplete.join(', ') }
              }}
            </p>
          }
          @if (s.records) {
            <div class="actions">
              @for (f of formats; track f) {
                <button mat-stroked-button type="button" [disabled]="busy()" (click)="download(f)">
                  {{ 'export.bibliography.format.' + f | transloco }}
                </button>
              }
            </div>
          }
        }
      </mat-card-content>
    </mat-card>
  `,
})
export class BibliographyCard implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly formats: BibFormat[] = ['ris', 'bibtex', 'vancouver'];
  protected readonly status = signal<BibStatus | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(async () => {
      this.status.set(await this.api.invoke(bibliographyStatus, { project_id: this.projectId() }));
    });
  }

  async download(file_format: BibFormat): Promise<void> {
    await this.guard(async () => {
      const response = await this.api.invoke$Response(exportBibliography, {
        project_id: this.projectId(),
        file_format,
      });
      saveFile(
        response.body,
        fileNameFrom(response.headers.get('content-disposition'), 'bibliography'),
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
}
