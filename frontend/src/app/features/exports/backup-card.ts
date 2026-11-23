import { Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { backupDownload } from '../../core/api/fn/backup/backup-download';
import { startBackup } from '../../core/api/fn/backup/start-backup';
import { withJsonBody } from '../../core/errors/problem';
import { JobProgressService } from '../../core/jobs/job-progress';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

/** Full project backup (data + PDFs) as a ZIP made in the background. Admin only. */
@Component({
  selector: 'rm-backup-card',
  imports: [TranslocoPipe, MatButtonModule, MatCardModule, MatProgressBarModule, FormError],
  template: `
    @if (isAdmin()) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>{{ 'export.backup.title' | transloco }}</h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <p>{{ 'export.backup.intro' | transloco }}</p>
          <rm-form-error [error]="error()" />
          @if (progress() !== null) {
            <mat-progress-bar mode="determinate" [value]="progress()" />
          }
          <button mat-flat-button type="button" [disabled]="busy()" (click)="run()">
            {{ 'export.backup.start' | transloco }}
          </button>
        </mat-card-content>
      </mat-card>
    }
  `,
})
export class BackupCard {
  private readonly api = inject(Api);
  private readonly jobs = inject(JobProgressService);
  private readonly context = inject(ProjectContext);

  protected readonly busy = signal(false);
  protected readonly progress = signal<number | null>(null);
  protected readonly error = signal<unknown>(null);
  protected readonly isAdmin = computed(
    () => this.context.project()?.my_roles?.includes('admin') ?? false,
  );

  async run(): Promise<void> {
    const project_id = this.context.project()!.id;
    this.busy.set(true);
    this.error.set(null);
    this.progress.set(0);
    try {
      const started = await this.api.invoke(startBackup, { project_id });
      const job = await this.jobs.follow(project_id, started.job_id, (j) =>
        this.progress.set(j.progress),
      );
      if (job.status !== 'succeeded') throw new Error(job.error_code ?? 'backup.failed');
      const link = await this.api.invoke(backupDownload, { project_id, job_id: started.job_id });
      const a = document.createElement('a');
      a.href = link.url;
      a.download = link.name;
      a.click();
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
      this.progress.set(null);
    }
  }
}
