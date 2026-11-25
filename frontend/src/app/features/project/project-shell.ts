import { Component, effect, inject, input } from '@angular/core';
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { FormError } from '../../shared/form-error';
import { ArchivedBanner } from './archived-banner';
import { ProjectContext } from './project-context';

@Component({
  selector: 'rm-project-shell',
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    TranslocoPipe,
    MatTabsModule,
    FormError,
    ArchivedBanner,
  ],
  providers: [ProjectContext],
  template: `
    <a routerLink="/projetos" class="back">← {{ 'projects.title' | transloco }}</a>
    @if (context.error()) {
      <rm-form-error [error]="context.error()" />
    } @else if (context.project(); as project) {
      <h1>{{ project.title }}</h1>
      <rm-archived-banner />
      <nav mat-tab-nav-bar [tabPanel]="panel" class="project-tabs">
        @for (tab of tabs; track tab.path) {
          <a
            mat-tab-link
            [routerLink]="tab.path"
            routerLinkActive
            #link="routerLinkActive"
            [active]="link.isActive"
          >
            {{ 'project.nav.' + tab.key | transloco }}
          </a>
        }
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
  /** In the order of the review: protocol to export, settings last. */
  protected readonly tabs = [
    { path: 'protocolo', key: 'protocol' },
    { path: 'buscas', key: 'searches' },
    { path: 'triagem', key: 'screening' },
    { path: 'estudos', key: 'studies' },
    { path: 'risco-de-vies', key: 'rob' },
    { path: 'pendencias', key: 'pending' },
    { path: 'conferencia', key: 'review' },
    { path: 'meta-analise', key: 'meta' },
    { path: 'grade', key: 'grade' },
    { path: 'prisma', key: 'prisma' },
    { path: 'resumo', key: 'abstract' },
    { path: 'exportar', key: 'export' },
    { path: 'configuracoes', key: 'settings' },
  ];
  protected readonly context = inject(ProjectContext);
  readonly projectId = input.required<string>();

  constructor() {
    effect(() => void this.context.load(this.projectId()));
  }
}
