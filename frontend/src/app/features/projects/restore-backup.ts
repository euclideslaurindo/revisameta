import { Component, inject, output, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { importProject } from '../../core/api/fn/backup/import-project';
import { withJsonBody } from '../../core/errors/problem';
import { JobProgressService } from '../../core/jobs/job-progress';
import { FormError } from '../../shared/form-error';

/** Creates a new project from a backup ZIP; whoever restores becomes its admin. */
@Component({
  selector: 'rm-restore-backup',
  imports: [TranslocoPipe, MatButtonModule, MatProgressBarModule, FormError],
  template: `
    <label class="restore">
      <span class="mat-mdc-button">{{ 'projects.restore.label' | transloco }}</span>
      <input
        type="file"
        accept=".zip,application/zip"
        [disabled]="busy()"
        (change)="pick($event)"
        [attr.aria-label]="'projects.restore.label' | transloco"
      />
    </label>
    @if (progress() !== null) {
      <mat-progress-bar mode="determinate" [value]="progress()" />
    }
    @if (absent().length) {
      <p class="warning" role="status">
        {{ 'projects.restore.absent' | transloco: { names: absent().join(', ') } }}
      </p>
    }
    <rm-form-error [error]="error()" />
  `,
  styles: `
    .restore input {
      margin-left: 8px;
    }
  `,
})
export class RestoreBackup {
  private readonly api = inject(Api);
  private readonly jobs = inject(JobProgressService);
  private readonly router = inject(Router);

  readonly restored = output<string>();
  protected readonly busy = signal(false);
  protected readonly progress = signal<number | null>(null);
  protected readonly absent = signal<string[]>([]);
  protected readonly error = signal<unknown>(null);

  async pick(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.busy.set(true);
    this.error.set(null);
    this.absent.set([]);
    this.progress.set(0);
    try {
      const started = await this.api.invoke(importProject, {
        body: { file: file as unknown as string },
      });
      const job = await this.jobs.follow(started.project_id, started.job_id, (j) =>
        this.progress.set(j.progress),
      );
      if (job.status !== 'succeeded') throw new Error(job.error_code ?? 'backup.failed');
      const absent = (job.result?.['absent_users'] as string[] | undefined) ?? [];
      this.absent.set(absent);
      this.restored.emit(started.project_id);
      if (!absent.length) await this.router.navigate(['/projetos', started.project_id]);
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
      this.progress.set(null);
      input.value = '';
    }
  }
}
