import { Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { decideReference } from '../../core/api/fn/screening/decide-reference';
import { getScreeningSettings } from '../../core/api/fn/screening/get-screening-settings';
import { markUseful } from '../../core/api/fn/screening/mark-useful';
import { referenceHistory } from '../../core/api/fn/screening/reference-history';
import { screeningCounts } from '../../core/api/fn/screening/screening-counts';
import { screeningQueue } from '../../core/api/fn/screening/screening-queue';
import { undoLastDecision } from '../../core/api/fn/screening/undo-last-decision';
import { ScreeningCounts } from '../../core/api/models/screening-counts';
import { ScreeningDecisionOut } from '../../core/api/models/screening-decision-out';
import { ScreeningQueueItem } from '../../core/api/models/screening-queue-item';
import { ScreeningSettings } from '../../core/api/models/screening-settings';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { LocalDatePipe } from '../../shared/local-date.pipe';
import { ProjectContext } from '../project/project-context';
import { listExclusionReasons } from '../../core/api/fn/screening/list-exclusion-reasons';
import { priorityInfo } from '../../core/api/fn/screening/priority-info';
import { trainPriority } from '../../core/api/fn/screening/train-priority';
import { PriorityInfo } from '../../core/api/models/priority-info';
import { JobProgressService } from '../../core/jobs/job-progress';
import { ReasonOut } from '../../core/api/models/reason-out';
import { ExclusionReasons, reasonText } from './exclusion-reasons';
import { highlight, Segment } from './highlight';
import { IncludedStudies } from './included-studies';
import { ScreeningAdmin, ScreeningAdminResolve } from './screening-admin';

type View = 'todo' | 'done' | 'conflicts' | 'all';
type Decision = 'include' | 'exclude' | 'maybe';

/**
 * Title and abstract screening (docs/modulos.md 7.3). One card at a time, with the same
 * three choices and the same keyboard shortcuts on any screen size (lesson L8).
 */
@Component({
  selector: 'rm-screening-page',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatButtonToggleModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
    LocalDatePipe,
    ExclusionReasons,
    IncludedStudies,
    ScreeningAdmin,
    ScreeningAdminResolve,
  ],
  template: `
    <h2>
      {{ 'screening.title' | transloco }}
      <span class="term" tabindex="0" [matTooltip]="'screening.help' | transloco">?</span>
    </h2>
    <p class="muted">{{ 'screening.intro' | transloco }}</p>
    <mat-button-toggle-group
      [(ngModel)]="stage"
      (ngModelChange)="reload()"
      [hideSingleSelectionIndicator]="true"
      [attr.aria-label]="'screening.stage.label' | transloco"
    >
      <mat-button-toggle value="title_abstract">{{
        'screening.stage.title_abstract' | transloco
      }}</mat-button-toggle>
      <mat-button-toggle value="full_text">{{
        'screening.stage.full_text' | transloco
      }}</mat-button-toggle>
    </mat-button-toggle-group>
    @if (stage === 'full_text') {
      <p class="muted">{{ 'screening.fullTextIntro' | transloco }}</p>
    }
    <rm-form-error [error]="error()" />
    @if (stage === 'title_abstract') {
      <div class="row">
        <mat-button-toggle-group
          [(ngModel)]="order"
          (ngModelChange)="reload()"
          [hideSingleSelectionIndicator]="true"
          [attr.aria-label]="'screening.priority.order' | transloco"
        >
          <mat-button-toggle value="import">{{
            'screening.priority.byImport' | transloco
          }}</mat-button-toggle>
          <mat-button-toggle value="priority" [disabled]="!priority()?.trained_at">{{
            'screening.priority.byPriority' | transloco
          }}</mat-button-toggle>
        </mat-button-toggle-group>
        <span class="term" tabindex="0" [matTooltip]="'screening.priority.help' | transloco"
          >?</span
        >
        @if (canScreen()) {
          <button mat-stroked-button type="button" [disabled]="busy()" (click)="train()">
            {{ 'screening.priority.train' | transloco }}
          </button>
        }
      </div>
      @if (priority(); as pr) {
        @if (pr.trained_at) {
          <p class="muted">
            {{
              'screening.priority.info'
                | transloco: { includes: pr.includes, excludes: pr.excludes, scored: pr.scored }
            }}
          </p>
        }
      }
      @if (priorityNote(); as note) {
        <p class="notice notice-warn" role="status">{{ note }}</p>
      }
      @if (order === 'priority') {
        <p class="notice notice-warn" role="status">
          {{ 'screening.priority.warning' | transloco }}
        </p>
      }
    }

    @if (counts(); as c) {
      <p>
        <strong>{{
          'screening.progress' | transloco: { done: c.decided_by_me, left: c.left_for_me }
        }}</strong>
        @if (c.include !== null && c.include !== undefined) {
          ·
          {{
            'screening.overall'
              | transloco
                : {
                    include: c.include,
                    exclude: c.exclude,
                    conflict: c.conflict,
                    pending: c.pending,
                  }
          }}
        }
      </p>
      @if (settings()?.blind) {
        <p class="muted">{{ 'screening.blindOn' | transloco }}</p>
      }
    }

    <div class="row">
      <mat-button-toggle-group
        [(ngModel)]="view"
        (ngModelChange)="reload()"
        [hideSingleSelectionIndicator]="true"
      >
        <mat-button-toggle value="todo">{{ 'screening.view.todo' | transloco }}</mat-button-toggle>
        <mat-button-toggle value="done">{{ 'screening.view.done' | transloco }}</mat-button-toggle>
        @if (seesAll()) {
          <mat-button-toggle value="conflicts">{{
            'screening.view.conflicts' | transloco
          }}</mat-button-toggle>
          <mat-button-toggle value="all">{{ 'screening.view.all' | transloco }}</mat-button-toggle>
        }
      </mat-button-toggle-group>
      <mat-form-field subscriptSizing="dynamic">
        <mat-label>{{ 'screening.search' | transloco }}</mat-label>
        <input matInput [(ngModel)]="q" (keyup.enter)="reload()" />
      </mat-form-field>
    </div>

    @if (current(); as item) {
      <mat-card class="block card">
        <mat-card-content>
          <p class="muted">
            {{ 'screening.position' | transloco: { n: index() + 1, total: total() } }}
          </p>
          <h3 class="ref-title">
            @for (s of segments(item.reference.title); track $index) {
              <span [class]="s.kind ? 'kw kw-' + s.kind : ''">{{ s.text }}</span>
            }
          </h3>
          <p class="muted">
            {{ item.reference.authors || '—' }} · {{ item.reference.year || '—' }}
            @if (item.reference.journal) {
              · {{ item.reference.journal }}
            }
            @if (item.reference.doi) {
              · DOI {{ item.reference.doi }}
            }
          </p>
          <p class="abstract">
            @if (item.reference.abstract) {
              @for (s of segments(item.reference.abstract); track $index) {
                <span [class]="s.kind ? 'kw kw-' + s.kind : ''">{{ s.text }}</span>
              }
            } @else {
              <span class="muted">{{ 'screening.noAbstract' | transloco }}</span>
            }
          </p>

          @if (item.my_decision) {
            <p>
              <span class="badge">{{
                'screening.mine'
                  | transloco: { d: ('screening.decision.' + item.my_decision | transloco) }
              }}</span>
            </p>
          }
          @if (item.status) {
            <p>
              <span class="badge">{{ 'screening.status.' + item.status | transloco }}</span>
              @for (o of item.others; track o.id) {
                <span class="muted">
                  {{ o.user_name }}: {{ 'screening.decision.' + o.decision | transloco }}</span
                >
              }
            </p>
          }

          @if (canScreen()) {
            <div class="decisions" role="group" [attr.aria-label]="'screening.decide' | transloco">
              <button
                mat-flat-button
                type="button"
                class="d-include"
                [disabled]="busy()"
                (click)="decide('include')"
              >
                {{ 'screening.decision.include' | transloco }} <kbd>I</kbd>
              </button>
              @if (stage === 'title_abstract') {
                <button
                  mat-flat-button
                  type="button"
                  class="d-maybe"
                  [disabled]="busy()"
                  (click)="decide('maybe')"
                >
                  {{ 'screening.decision.maybe' | transloco }} <kbd>T</kbd>
                </button>
              }
              <button
                mat-flat-button
                type="button"
                class="d-exclude"
                [disabled]="busy()"
                (click)="decide('exclude')"
              >
                {{ 'screening.decision.exclude' | transloco }} <kbd>E</kbd>
              </button>
            </div>
            @if (stage === 'full_text') {
              <mat-form-field class="full" subscriptSizing="dynamic">
                <mat-label>{{ 'screening.reasonToExclude' | transloco }}</mat-label>
                <mat-select [(ngModel)]="reasonId">
                  @for (r of activeReasons(); track r.id) {
                    <mat-option [value]="r.id">{{ reasonLabel(r) }}</mat-option>
                  }
                </mat-select>
                <mat-hint>{{ 'screening.reasonHint' | transloco }}</mat-hint>
              </mat-form-field>
            }
            <mat-form-field class="full" subscriptSizing="dynamic">
              <mat-label>{{ 'screening.note' | transloco }}</mat-label>
              <input matInput maxlength="1000" [(ngModel)]="note" />
            </mat-form-field>
            <div class="row">
              <mat-checkbox
                [checked]="item.useful_as_reference"
                (change)="useful(item, $event.checked)"
              >
                {{ 'screening.useful' | transloco }}
              </mat-checkbox>
              <span class="term" tabindex="0" [matTooltip]="'screening.usefulHelp' | transloco"
                >?</span
              >
            </div>
          }
          <div class="actions">
            <button
              mat-button
              type="button"
              [disabled]="busy() || index() === 0"
              (click)="move(-1)"
            >
              ← {{ 'screening.previous' | transloco }}
            </button>
            <button mat-button type="button" [disabled]="busy()" (click)="move(1)">
              {{ 'screening.next' | transloco }} →
            </button>
            @if (canScreen()) {
              <button mat-button type="button" [disabled]="busy()" (click)="undo()">
                {{ 'screening.undo' | transloco }} <kbd>U</kbd>
              </button>
            }
            <button mat-button type="button" [disabled]="busy()" (click)="showHistory(item)">
              {{ 'screening.history' | transloco }}
            </button>
          </div>
          @if (history().length) {
            <ul class="item-list">
              @for (h of history(); track h.id) {
                <li [class.muted]="!h.current">
                  {{ h.created_at | localDate }} ·
                  {{ h.user_name || ('screening.you' | transloco) }}:
                  {{ 'screening.decision.' + h.decision | transloco }}
                  @if (h.undone) {
                    ({{ 'screening.undone' | transloco }})
                  } @else if (!h.current) {
                    ({{ 'screening.replaced' | transloco }})
                  }
                  @if (h.note) {
                    — {{ h.note }}
                  }
                </li>
              }
            </ul>
          }
          <p class="muted small">{{ 'screening.shortcuts' | transloco }}</p>
        </mat-card-content>
      </mat-card>
      @if (view === 'conflicts' && context.isAdmin()) {
        <rm-screening-admin-resolve
          [referenceId]="item.reference.id"
          [stage]="stage"
          [reasons]="activeReasons()"
          (resolved)="reload()"
        />
      }
    } @else if (loaded()) {
      <p class="muted">{{ 'screening.emptyView.' + view | transloco }}</p>
    }

    @if (context.isAdmin()) {
      <rm-screening-admin [stage]="stage" (changed)="reload()" />
      @if (stage === 'full_text') {
        <rm-exclusion-reasons (changed)="loadReasons()" />
        <rm-included-studies />
      }
    }
  `,
  styles: `
    .card {
      max-width: 900px;
    }
    .ref-title {
      margin-top: 0;
    }
    .abstract {
      white-space: pre-line;
      line-height: 1.5;
    }
    .kw-include {
      background: #c8f0c8;
      color: #0b4d0b;
      border-radius: 2px;
    }
    .kw-exclude {
      background: #f7c9c9;
      color: #6b0d0d;
      border-radius: 2px;
    }
    .decisions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0;
    }
    .decisions button {
      flex: 1 1 140px;
    }
    .d-include {
      background: #2e7d32 !important;
      color: #fff !important;
    }
    .d-maybe {
      background: #f9a825 !important;
      color: #000 !important;
    }
    .d-exclude {
      background: #c62828 !important;
      color: #fff !important;
    }
    kbd {
      font-size: 0.75em;
      opacity: 0.8;
      margin-left: 4px;
    }
    .full {
      width: 100%;
    }
    .small {
      font-size: 0.85em;
    }
  `,
})
export class ScreeningPage implements OnInit {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly jobs = inject(JobProgressService);
  protected readonly context = inject(ProjectContext);

  protected stage: 'title_abstract' | 'full_text' = 'title_abstract';
  protected reasonId: string | null = null;
  protected readonly reasons = signal<ReasonOut[]>([]);
  protected readonly activeReasons = computed(() =>
    this.reasons().filter((r) => !r.merged_into_id),
  );
  protected order: 'import' | 'priority' = 'import';
  protected readonly priority = signal<PriorityInfo | null>(null);
  protected readonly priorityNote = signal<string | null>(null);
  protected view: View = 'todo';
  protected q = '';
  protected note = '';
  protected readonly items = signal<ScreeningQueueItem[]>([]);
  protected readonly index = signal(0);
  protected readonly total = signal(0);
  protected readonly nextCursor = signal<string | null>(null);
  protected readonly counts = signal<ScreeningCounts | null>(null);
  protected readonly settings = signal<ScreeningSettings | null>(null);
  protected readonly history = signal<ScreeningDecisionOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly loaded = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly current = computed(() => this.items()[this.index()] ?? null);
  protected readonly canScreen = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.includes('admin') || roles.includes('reviewer');
  });
  protected readonly seesAll = computed(() => this.context.isAdmin() || !this.settings()?.blind);

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(async () => {
      this.settings.set(
        await this.api.invoke(getScreeningSettings, { project_id: this.projectId() }),
      );
      await this.fetch(true);
    });
  }

  protected reasonLabel(r: ReasonOut): string {
    return reasonText(r, (k) => this.transloco.translate(k));
  }

  async train(): Promise<void> {
    await this.guard(async () => {
      this.priorityNote.set(null);
      const started = await this.api.invoke(trainPriority, { project_id: this.projectId() });
      if (started.job_id) {
        const job = await this.jobs.follow(this.projectId(), started.job_id, () => undefined);
        if (job.status === 'failed') {
          this.priorityNote.set(
            this.transloco.translate('screening.priority.needs', {
              min: started.min_each,
              includes: (job.result as Record<string, number> | null)?.['includes'] ?? 0,
              excludes: (job.result as Record<string, number> | null)?.['excludes'] ?? 0,
            }),
          );
          return;
        }
      }
      this.priority.set(await this.api.invoke(priorityInfo, { project_id: this.projectId() }));
      this.order = 'priority';
      await this.fetch(true);
    });
  }

  async loadReasons(): Promise<void> {
    this.reasons.set(await this.api.invoke(listExclusionReasons, { project_id: this.projectId() }));
  }

  protected segments(text: string): Segment[] {
    const s = this.settings();
    return highlight(text, s?.include_keywords ?? [], s?.exclude_keywords ?? []);
  }

  async reload(): Promise<void> {
    await this.guard(async () => {
      if (this.stage === 'full_text') await this.loadReasons();
      this.priority.set(await this.api.invoke(priorityInfo, { project_id: this.projectId() }));
      this.settings.set(
        await this.api.invoke(getScreeningSettings, { project_id: this.projectId() }),
      );
      await this.fetch(true);
    });
  }

  private async fetch(reset: boolean): Promise<void> {
    const page = await this.api.invoke(screeningQueue, {
      project_id: this.projectId(),
      stage: this.stage,
      view: this.view,
      limit: 50,
      after: reset || this.order === 'priority' ? undefined : (this.nextCursor() ?? undefined),
      q: this.q.trim() || undefined,
      order: this.stage === 'title_abstract' ? this.order : 'import',
      // Priority order pages by position; decided references leave the list, so the
      // position of the next page is how many are still loaded.
      offset: reset ? 0 : this.items().length,
    });
    this.items.set(reset ? page.items : [...this.items(), ...page.items]);
    if (reset) this.index.set(0);
    this.total.set(page.total);
    this.nextCursor.set(
      this.order === 'priority' && this.stage === 'title_abstract'
        ? page.next_offset !== null && page.next_offset !== undefined
          ? 'more'
          : null
        : (page.next_cursor ?? null),
    );
    this.counts.set(
      await this.api.invoke(screeningCounts, { project_id: this.projectId(), stage: this.stage }),
    );
    this.history.set([]);
    this.loaded.set(true);
  }

  async decide(decision: Decision): Promise<void> {
    const item = this.current();
    if (!item || !this.canScreen()) return;
    if (this.stage === 'full_text' && decision === 'maybe') return;
    await this.guard(async () => {
      await this.api.invoke(decideReference, {
        project_id: this.projectId(),
        stage: this.stage,
        reference_id: item.reference.id,
        body: {
          decision,
          note: this.note.trim() || null,
          exclusion_reason_id: decision === 'exclude' ? this.reasonId : null,
        },
      });
      this.note = '';
      this.reasonId = null;
      if (this.view === 'todo') {
        // The decided reference leaves the "to do" list: stay on the same position.
        const rest = this.items().filter((i) => i.reference.id !== item.reference.id);
        this.items.set(rest);
        this.total.update((t) => Math.max(0, t - 1));
        if (this.index() >= rest.length) this.index.set(Math.max(0, rest.length - 1));
        if (rest.length < 5 && this.nextCursor()) await this.fetch(false);
        this.counts.set(
          await this.api.invoke(screeningCounts, {
            project_id: this.projectId(),
            stage: this.stage,
          }),
        );
      } else {
        await this.fetch(true);
      }
      this.history.set([]);
    });
  }

  async undo(): Promise<void> {
    await this.guard(async () => {
      const back = await this.api.invoke(undoLastDecision, {
        project_id: this.projectId(),
        stage: this.stage,
      });
      await this.fetch(true);
      const position = this.items().findIndex((i) => i.reference.id === back?.reference_id);
      if (position >= 0) this.index.set(position);
    });
  }

  async move(step: number): Promise<void> {
    const next = this.index() + step;
    if (next < 0) return;
    if (next >= this.items().length && this.nextCursor()) {
      await this.guard(() => this.fetch(false));
    }
    if (next < this.items().length) {
      this.index.set(next);
      this.history.set([]);
      this.note = '';
    }
  }

  async useful(item: ScreeningQueueItem, value: boolean): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(markUseful, {
        project_id: this.projectId(),
        reference_id: item.reference.id,
        body: { useful: value },
      });
      this.items.update((list) =>
        list.map((i) =>
          i.reference.id === item.reference.id ? { ...i, useful_as_reference: value } : i,
        ),
      );
    });
  }

  async showHistory(item: ScreeningQueueItem): Promise<void> {
    await this.guard(async () => {
      this.history.set(
        await this.api.invoke(referenceHistory, {
          project_id: this.projectId(),
          stage: this.stage,
          reference_id: item.reference.id,
        }),
      );
    });
  }

  /** Same shortcuts everywhere: I include, E exclude, T maybe (also 1/2/3), U undo, arrows move. */
  @HostListener('document:keydown', ['$event'])
  onKey(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
    if (event.ctrlKey || event.metaKey || event.altKey || this.busy()) return;
    const key = event.key.toLowerCase();
    const map: Record<string, () => void> = {
      i: () => void this.decide('include'),
      '1': () => void this.decide('include'),
      e: () => void this.decide('exclude'),
      '2': () => void this.decide('exclude'),
      t: () => void this.decide('maybe'),
      m: () => void this.decide('maybe'),
      '3': () => void this.decide('maybe'),
      u: () => void this.undo(),
      arrowright: () => void this.move(1),
      arrowleft: () => void this.move(-1),
    };
    const action = map[key];
    if (action) {
      event.preventDefault();
      action();
    }
  }

  protected t(key: string, params?: Record<string, unknown>): string {
    return this.transloco.translate(key, params);
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
