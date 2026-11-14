import { Injectable, computed, inject, signal } from '@angular/core';

import { Api } from '../../core/api/api';
import { getProject } from '../../core/api/fn/projects/get-project';
import { ProjectOut } from '../../core/api/models/project-out';

/** The project currently open, shared by the pages inside /projetos/:projectId. */
@Injectable()
export class ProjectContext {
  private readonly api = inject(Api);

  readonly project = signal<ProjectOut | null>(null);
  readonly error = signal<unknown>(null);
  readonly isAdmin = computed(() => this.project()?.my_roles?.includes('admin') ?? false);

  async load(projectId: string): Promise<void> {
    this.error.set(null);
    try {
      this.project.set(await this.api.invoke(getProject, { project_id: projectId }));
    } catch (error) {
      this.project.set(null);
      this.error.set(error);
    }
  }

  update(project: ProjectOut): void {
    this.project.set({ ...project, my_roles: project.my_roles ?? this.project()?.my_roles });
  }
}
