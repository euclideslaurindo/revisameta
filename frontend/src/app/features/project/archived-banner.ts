import { Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { unarchiveProject } from '../../core/api/fn/backup/unarchive-project';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { LocalDatePipe } from '../../shared/local-date.pipe';
import { ProjectContext } from './project-context';

/** Shown on archived projects (12 months without changes): only a mark, reversible. */
@Component({
  selector: 'rm-archived-banner',
  imports: [TranslocoPipe, MatButtonModule, FormError, LocalDatePipe],
  template: `
    @if (archivedAt(); as at) {
      <div class="warning" role="status">
        {{ 'project.archived.text' | transloco: { date: (at | localDate) } }}
        @if (isAdmin()) {
          <button mat-stroked-button type="button" [disabled]="busy()" (click)="unarchive()">
            {{ 'project.archived.unarchive' | transloco }}
          </button>
        }
        <rm-form-error [error]="error()" />
      </div>
    }
  `,
})
export class ArchivedBanner {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly archivedAt = computed(() => this.context.project()?.archived_at ?? null);
  protected readonly isAdmin = computed(
    () => this.context.project()?.my_roles?.includes('admin') ?? false,
  );

  async unarchive(): Promise<void> {
    const project = this.context.project();
    if (!project) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.invoke(unarchiveProject, { project_id: project.id });
      await this.context.load(project.id);
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }
}
