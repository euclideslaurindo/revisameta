import { Component, effect, inject, input } from '@angular/core';
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { FormError } from '../../shared/form-error';
import { ProjectContext } from './project-context';

@Component({
  selector: 'rm-project-shell',
  imports: [RouterLink, RouterLinkActive, RouterOutlet, TranslocoPipe, MatTabsModule, FormError],
  providers: [ProjectContext],
  template: `
    <a routerLink="/projetos" class="back">← {{ 'projects.title' | transloco }}</a>
    @if (context.error()) {
      <rm-form-error [error]="context.error()" />
    } @else if (context.project(); as project) {
      <h1>{{ project.title }}</h1>
      <nav mat-tab-nav-bar [tabPanel]="panel">
        <a mat-tab-link routerLink="protocolo" routerLinkActive #protocol="routerLinkActive" [active]="protocol.isActive">
          {{ 'project.nav.protocol' | transloco }}
        </a>
      </nav>
      <mat-tab-nav-panel #panel>
        <router-outlet />
      </mat-tab-nav-panel>
    } @else {
      <p role="status">{{ 'common.loading' | transloco }}</p>
    }
  `,
})
export class ProjectShell {
  protected readonly context = inject(ProjectContext);
  readonly projectId = input.required<string>();

  constructor() {
    effect(() => void this.context.load(this.projectId()));
  }
}
