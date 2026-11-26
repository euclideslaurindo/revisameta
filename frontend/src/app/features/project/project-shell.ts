import { Component, DestroyRef, effect, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { filter } from 'rxjs';

import { Api } from '../../core/api/api';
import { projectDashboard } from '../../core/api/fn/dashboard/project-dashboard';
import { StageOut } from '../../core/api/models/stage-out';
import { FormError } from '../../shared/form-error';
import { ArchivedBanner } from './archived-banner';
import { ProjectContext } from './project-context';

interface NavItem {
  path: string;
  key: string;
  /** Dashboard stage whose state is shown next to the item. */
  stage?: StageOut['key'];
}
interface NavGroup {
  key: string;
  items: NavItem[];
}

/** The review's workflow, grouped as in the Learning page (protocol → report). */
const GROUPS: NavGroup[] = [
  { key: 'overview', items: [{ path: 'painel', key: 'dashboard' }] },
  { key: 'planning', items: [{ path: 'protocolo', key: 'protocol', stage: 'protocol' }] },
  {
    key: 'search',
    items: [
      { path: 'buscas', key: 'searches' },
      { path: 'triagem', key: 'screening', stage: 'screening' },
    ],
  },
  {
    key: 'data',
    items: [
      { path: 'estudos', key: 'studies', stage: 'extraction' },
      { path: 'pendencias', key: 'pending' },
      { path: 'conferencia', key: 'review' },
    ],
  },
  { key: 'bias', items: [{ path: 'risco-de-vies', key: 'rob', stage: 'rob' }] },
  {
    key: 'analysis',
    items: [
      { path: 'meta-analise', key: 'meta', stage: 'analysis' },
      { path: 'grade', key: 'grade', stage: 'grade' },
    ],
  },
  {
    key: 'report',
    items: [
      { path: 'prisma', key: 'prisma' },
      { path: 'resumo', key: 'abstract' },
      { path: 'exportar', key: 'export' },
    ],
  },
];

@Component({
  selector: 'rm-project-shell',
  imports: [RouterLink, RouterLinkActive, RouterOutlet, TranslocoPipe, FormError, ArchivedBanner],
  providers: [ProjectContext],
  template: `
    @if (context.error()) {
      <a routerLink="/projetos" class="back">← {{ 'projects.title' | transloco }}</a>
      <rm-form-error [error]="context.error()" />
    } @else if (context.project(); as project) {
      <div class="project-layout" [class.menu-open]="menuOpen()">
        <aside class="project-side">
          <a routerLink="/projetos" class="back">← {{ 'projects.title' | transloco }}</a>
          <button
            type="button"
            class="menu-toggle"
            [attr.aria-expanded]="menuOpen()"
            aria-controls="project-nav"
            (click)="menuOpen.set(!menuOpen())"
          >
            ☰ {{ 'project.nav.menu' | transloco }}
          </button>
          <nav id="project-nav" [attr.aria-label]="'project.nav.label' | transloco">
            @for (group of groups; track group.key) {
              <p class="group">{{ 'project.nav.groups.' + group.key | transloco }}</p>
              <ul>
                @for (item of group.items; track item.path) {
                  <li>
                    <a
                      [routerLink]="item.path"
                      routerLinkActive="active"
                      ariaCurrentWhenActive="page"
                      (click)="menuOpen.set(false)"
                    >
                      <span>{{ 'project.nav.' + item.key | transloco }}</span>
                      @if (item.stage && stateOf(item.stage); as state) {
                        <span
                          class="stage-dot"
                          [class]="'stage-dot ' + state"
                          [title]="'dashboard.state.' + state | transloco"
                        >
                          <span class="sr-only">{{ 'dashboard.state.' + state | transloco }}</span>
                        </span>
                      }
                    </a>
                  </li>
                }
              </ul>
            }
            <ul class="settings">
              <li>
                <a
                  routerLink="configuracoes"
                  routerLinkActive="active"
                  (click)="menuOpen.set(false)"
                >
                  ⚙ {{ 'project.nav.settings' | transloco }}
                </a>
              </li>
            </ul>
          </nav>
        </aside>
        <section class="project-main">
          <h1>{{ project.title }}</h1>
          <rm-archived-banner />
          <router-outlet />
        </section>
      </div>
    } @else {
      <p role="status">{{ 'common.loading' | transloco }}</p>
    }
  `,
})
export class ProjectShell {
  private readonly api = inject(Api);
  protected readonly groups = GROUPS;
  protected readonly context = inject(ProjectContext);
  protected readonly menuOpen = signal(false);
  private readonly stages = signal<Partial<Record<StageOut['key'], StageOut['state']>>>({});
  readonly projectId = input.required<string>();

  constructor() {
    effect(() => {
      const id = this.projectId();
      void this.context.load(id);
      void this.loadStages(id);
    });
    // Stage states change as people work; refresh them on every page change.
    inject(Router)
      .events.pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe(() => void this.loadStages(this.projectId()));
  }

  protected stateOf(key: StageOut['key']): StageOut['state'] | undefined {
    return this.stages()[key];
  }

  private async loadStages(projectId: string): Promise<void> {
    try {
      const dashboard = await this.api.invoke(projectDashboard, { project_id: projectId });
      this.stages.set(Object.fromEntries(dashboard.stages.map((s) => [s.key, s.state])));
    } catch {
      // The menu works without the states.
    }
  }
}
