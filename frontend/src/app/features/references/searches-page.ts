import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { deleteSearch } from '../../core/api/fn/references/delete-search';
import { getSearch } from '../../core/api/fn/references/get-search';
import { importSearch } from '../../core/api/fn/references/import-search';
import { listReferences } from '../../core/api/fn/references/list-references';
import { listSearches } from '../../core/api/fn/references/list-searches';
import { SearchReferenceOut } from '../../core/api/models/search-reference-out';
import { SearchDetail } from '../../core/api/models/search-detail';
import { SearchOut } from '../../core/api/models/search-out';
import { withJsonBody } from '../../core/errors/problem';
import { JobProgressService } from '../../core/jobs/job-progress';
import { FormError } from '../../shared/form-error';
import { LocalDatePipe } from '../../shared/local-date.pipe';
import { ProjectContext } from '../project/project-context';

/**
 * Searches (docs/modulos.md 7.2, stage 5 step 1): import a database export with the
 * date and the strategy, follow the progress, see which records could not be read.
 */
import { AiSearchHelp } from './ai-search-help';

@Component({
  selector: 'rm-searches-page',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatExpansionModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    MatTooltipModule,
    FormError,
    LocalDatePipe,
    AiSearchHelp,
  ],
  template: `
    <rm-ai-search-help />
    <h2>{{ 'searches.title' | transloco }}</h2>
    <p class="muted">{{ 'searches.intro' | transloco }}</p>
    @if (searches().length) {
      <p>
        <a routerLink="duplicatas">{{ 'searches.toDuplicates' | transloco }} →</a>
      </p>
    }
    <rm-form-error [error]="error()" />

    @if (canImport()) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>{{ 'searches.new' | transloco }}</h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <div class="row">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'searches.database' | transloco }}</mat-label>
              <input matInput maxlength="100" [(ngModel)]="database" />
            </mat-form-field>
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'searches.date' | transloco }}</mat-label>
              <input matInput type="date" [(ngModel)]="searchDate" />
            </mat-form-field>
          </div>
          <mat-form-field class="full">
            <mat-label>{{ 'searches.strategy' | transloco }}</mat-label>
            <textarea matInput rows="3" [(ngModel)]="strategy"></textarea>
            <mat-hint>{{ 'searches.strategyHint' | transloco }}</mat-hint>
          </mat-form-field>
          <label class="file-input">
            <span>{{ 'searches.file' | transloco }}</span>
            <input type="file" accept=".ris,.nbib,.txt,.bib,.csv,.enw" (change)="choose($event)" />
          </label>
          <p class="muted">{{ 'searches.formats' | transloco }}</p>
          <div class="actions">
            <button
              mat-flat-button
              type="button"
              [disabled]="busy() || !file || !database.trim() || !searchDate"
              (click)="upload()"
            >
              {{ 'searches.import' | transloco }}
            </button>
          </div>
          @if (progress() !== null) {
            <mat-progress-bar mode="determinate" [value]="progress()" />
            <p class="muted" role="status">
              {{ 'searches.progress' | transloco: { value: progress() } }}
            </p>
          }
        </mat-card-content>
      </mat-card>
    }

    @if (!searches().length) {
      <p class="muted">{{ 'searches.empty' | transloco }}</p>
    } @else {
      <p>
        <strong>{{ 'searches.total' | transloco: { count: totalRecords() } }}</strong>
      </p>
      <mat-accordion>
        @for (s of searches(); track s.id) {
          <mat-expansion-panel (opened)="open(s)">
            <mat-expansion-panel-header>
              <mat-panel-title>{{ s.database }} · {{ s.search_date | localDate }}</mat-panel-title>
              <mat-panel-description>
                {{ 'searches.status.' + s.status | transloco }} ·
                {{ 'searches.records' | transloco: { count: s.record_count } }}
                @if (s.error_count) {
                  · {{ 'searches.skipped' | transloco: { count: s.error_count } }}
                }
              </mat-panel-description>
            </mat-expansion-panel-header>
            <p class="muted">{{ s.filename }} ({{ s.file_format.toUpperCase() }})</p>
            @if (s.strategy) {
              <pre class="strategy">{{ s.strategy }}</pre>
            }
            @if (detail(); as d) {
              @if (d.id === s.id && d.errors.length) {
                <h4>{{ 'searches.report' | transloco }}</h4>
                <ul class="item-list">
                  @for (e of d.errors; track $index) {
                    <li [class]="e['skipped'] ? 'alert-item' : 'muted'">
                      {{ 'searches.record' | transloco: { number: e['number'] } }}:
                      {{ e['code'] | transloco }}
                      {{
                        (e['skipped'] ? 'searches.notImported' : 'searches.imported') | transloco
                      }}
                    </li>
                  }
                </ul>
                @if (d.error_count + d.warning_count > d.errors.length) {
                  <p class="muted">{{ 'searches.reportCut' | transloco }}</p>
                }
              }
            }
            @if (refs().length && refsFor() === s.id) {
              <h4>{{ 'searches.preview' | transloco }}</h4>
              <ol class="item-list">
                @for (r of refs(); track r.id) {
                  <li>
                    <strong>{{ r.title }}</strong>
                    <div class="muted">
                      {{ r.authors || '—' }} · {{ r.year || '—' }}
                      @if (r.journal) {
                        · {{ r.journal }}
                      }
                      @if (r.doi) {
                        · DOI {{ r.doi }}
                      }
                    </div>
                  </li>
                }
              </ol>
              @if (nextCursor()) {
                <button mat-stroked-button type="button" [disabled]="busy()" (click)="more(s)">
                  {{ 'searches.more' | transloco }}
                </button>
              }
            }
            @if (canImport() && (s.status === 'done' || s.status === 'failed')) {
              <div class="actions">
                <button mat-stroked-button type="button" [disabled]="busy()" (click)="remove(s)">
                  {{ 'searches.remove' | transloco }}
                </button>
              </div>
            }
          </mat-expansion-panel>
        }
      </mat-accordion>
    }
  `,
  styles: `
    .full {
      width: 100%;
    }
    .strategy {
      white-space: pre-wrap;
      font-size: 0.9em;
    }
  `,
})
export class SearchesPage implements OnInit {
  private readonly api = inject(Api);
  private readonly jobs = inject(JobProgressService);
  private readonly context = inject(ProjectContext);
  private readonly transloco = inject(TranslocoService);

  protected readonly searches = signal<SearchOut[]>([]);
  protected readonly detail = signal<SearchDetail | null>(null);
  protected readonly refs = signal<SearchReferenceOut[]>([]);
  protected readonly refsFor = signal<string | null>(null);
  protected readonly nextCursor = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected readonly progress = signal<number | null>(null);
  protected readonly error = signal<unknown>(null);
  protected readonly totalRecords = computed(() =>
    this.searches().reduce((sum, s) => sum + s.record_count, 0),
  );
  protected readonly canImport = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.includes('admin') || roles.includes('reviewer');
  });

  protected database = '';
  protected searchDate = new Date().toISOString().slice(0, 10);
  protected strategy = '';
  protected file: File | null = null;

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(() => this.load());
  }

  private async load(): Promise<void> {
    this.searches.set(await this.api.invoke(listSearches, { project_id: this.projectId() }));
  }

  protected choose(event: Event): void {
    this.file = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  async upload(): Promise<void> {
    const file = this.file;
    if (!file) return;
    await this.guard(async () => {
      const search = await this.api.invoke(importSearch, {
        project_id: this.projectId(),
        body: {
          file: file as unknown as string,
          database: this.database.trim(),
          search_date: this.searchDate,
          strategy: this.strategy.trim() || null,
        },
      });
      this.progress.set(0);
      if (search.job_id) {
        await this.jobs.follow(this.projectId(), search.job_id, (job) =>
          this.progress.set(job.progress),
        );
      }
      this.progress.set(null);
      this.file = null;
      await this.load();
    });
  }

  async open(s: SearchOut): Promise<void> {
    await this.guard(async () => {
      this.detail.set(
        await this.api.invoke(getSearch, { project_id: this.projectId(), search_id: s.id }),
      );
      const page = await this.api.invoke(listReferences, {
        project_id: this.projectId(),
        search_id: s.id,
        limit: 50,
      });
      this.refs.set(page.items);
      this.refsFor.set(s.id);
      this.nextCursor.set(page.next_cursor ?? null);
    });
  }

  async more(s: SearchOut): Promise<void> {
    const after = this.nextCursor();
    if (!after) return;
    await this.guard(async () => {
      const page = await this.api.invoke(listReferences, {
        project_id: this.projectId(),
        search_id: s.id,
        after,
        limit: 50,
      });
      this.refs.update((list) => [...list, ...page.items]);
      this.nextCursor.set(page.next_cursor ?? null);
    });
  }

  async remove(s: SearchOut): Promise<void> {
    const text = this.transloco.translate('searches.confirmRemove', { database: s.database });
    if (!window.confirm(text)) return;
    await this.guard(async () => {
      await this.api.invoke(deleteSearch, { project_id: this.projectId(), search_id: s.id });
      this.refs.set([]);
      await this.load();
    });
  }

  private async guard(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
    } catch (error) {
      this.error.set(await withJsonBody(error));
      this.progress.set(null);
    } finally {
      this.busy.set(false);
    }
  }
}
