import { Component, DestroyRef, computed, effect, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { filter } from 'rxjs';
import { Skeleton } from '../../shared/skeleton';

import { Api } from '../../core/api/api';
import { projectDashboard } from '../../core/api/fn/dashboard/project-dashboard';
import { PersonPending } from '../../core/api/models/person-pending';
import { StageOut } from '../../core/api/models/stage-out';
import { AuthService } from '../../core/auth/auth';
import { FormError } from '../../shared/form-error';
import { ArchivedBanner } from './archived-banner';
import { ProjectContext } from './project-context';
import { StepGuide, StepPager } from './step-guide';

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
  imports: [
    Skeleton,
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    TranslocoPipe,
    FormError,
    ArchivedBanner,
    StepGuide,
    StepPager,
  ],
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
          @if (myPending(); as mine) {
            <a class="my-pending" [routerLink]="mine.path" (click)="menuOpen.set(false)">
              <strong>{{ 'project.nav.mine' | transloco }}</strong>
              <span>{{ 'project.nav.mineCount' | transloco: { count: mine.total } }}</span>
            </a>
          }
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
                      @if (item.stage && stageOf(item.stage); as st) {
                        <span class="stage-progress" [class]="'stage-progress ' + st.state">
                          <span class="bar"
                            ><span
                              [style.width.%]="st.total ? (100 * st.done) / st.total : 0"
                            ></span
                          ></span>
                          <span class="count" aria-hidden="true">{{ st.done }}/{{ st.total }}</span>
                          <span class="sr-only"
                            >{{ 'dashboard.state.' + st.state | transloco }}: {{ st.done }}/{{
                              st.total
                            }}</span
                          >
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
          <rm-step-guide [key]="guideKey()" />
          <router-outlet />
          @if (guideKey()) {
            <rm-step-pager [previous]="neighbour(-1)" [next]="neighbour(1)" />
          }
        </section>
      </div>
    } @else {
      <rm-skeleton [lines]="[36, 120, 200]" />
    }
  `,
})
export class ProjectShell {
  private readonly api = inject(Api);
  protected readonly groups = GROUPS;
  protected readonly context = inject(ProjectContext);
  protected readonly menuOpen = signal(false);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly stages = signal<Partial<Record<StageOut['key'], StageOut>>>({});
  private readonly people = signal<PersonPending[]>([]);
  /** First path segment after the project id (e.g. "meta-analise"), or null on sub-pages. */
  private readonly section = signal<string | null>(null);
  readonly projectId = input.required<string>();

  private readonly items: NavItem[] = [
    ...GROUPS.flatMap((g) => g.items),
    { path: 'configuracoes', key: 'settings' },
  ];
  /** Guide and pager show on the main page of each step, not on detail pages. */
  protected readonly guideKey = computed(() => {
    const item = this.items.find((i) => i.path === this.section());
    return item ? item.key : null;
  });
  protected readonly myPending = computed(() => {
    const me = this.people().find((p) => p.user_id === this.auth.user()?.id);
    if (!me) return null;
    const total = me.screening_left + me.extractions_open + me.rob_open;
    if (!total) return null;
    const path = me.screening_left ? 'triagem' : me.extractions_open ? 'estudos' : 'risco-de-vies';
    return { total, path };
  });

  constructor() {
    effect(() => {
      const id = this.projectId();
      void this.context.load(id);
      void this.loadStages(id);
    });
    // Stage states change as people work; refresh them on every page change.
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe(() => {
        this.readSection();
        void this.loadStages(this.projectId());
      });
    this.readSection();
  }

  private readSection(): void {
    const path = this.router.url.split('?')[0].split('#')[0];
    const parts = path.split('/').filter(Boolean); // projetos, id, section, ...
    this.section.set(parts.length === 3 ? parts[2] : null);
  }

  protected neighbour(step: number): { path: string; label: string } | null {
    const i = this.items.findIndex((x) => x.path === this.section());
    const item = i < 0 ? undefined : this.items[i + step];
    return item ? { path: item.path, label: 'project.nav.' + item.key } : null;
  }

  protected stageOf(key: StageOut['key']): StageOut | undefined {
    return this.stages()[key];
  }

  private async loadStages(projectId: string): Promise<void> {
    try {
      const dashboard = await this.api.invoke(projectDashboard, { project_id: projectId });
      this.stages.set(Object.fromEntries(dashboard.stages.map((s) => [s.key, s])));
      this.people.set(dashboard.people);
    } catch {
      // The menu works without the states.
    }
  }
}
