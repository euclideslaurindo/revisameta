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
        <a
          mat-tab-link
          routerLink="protocolo"
          routerLinkActive
          #protocol="routerLinkActive"
          [active]="protocol.isActive"
        >
          {{ 'project.nav.protocol' | transloco }}
        </a>
        <a
          mat-tab-link
          routerLink="estudos"
          routerLinkActive
          #studies="routerLinkActive"
          [active]="studies.isActive"
        >
          {{ 'project.nav.studies' | transloco }}
        </a>
        <a
          mat-tab-link
          routerLink="pendencias"
          routerLinkActive
          #pending="routerLinkActive"
          [active]="pending.isActive"
        >
          {{ 'project.nav.pending' | transloco }}
        </a>
        <a
          mat-tab-link
          routerLink="risco-de-vies"
          routerLinkActive
          #rob="routerLinkActive"
          [active]="rob.isActive"
        >
          {{ 'project.nav.rob' | transloco }}
        </a>
        <a
          mat-tab-link
          routerLink="conferencia"
          routerLinkActive
          #review="routerLinkActive"
          [active]="review.isActive"
        >
          {{ 'project.nav.review' | transloco }}
        </a>
        <a
          mat-tab-link
          routerLink="meta-analise"
          routerLinkActive
          #meta="routerLinkActive"
          [active]="meta.isActive"
        >
          {{ 'project.nav.meta' | transloco }}
        </a>
        <a
          mat-tab-link
          routerLink="exportar"
          routerLinkActive
          #exports="routerLinkActive"
          [active]="exports.isActive"
        >
          {{ 'project.nav.export' | transloco }}
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
