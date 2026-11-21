import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { confirmCertainDuplicates } from '../../core/api/fn/references/confirm-certain-duplicates';
import { decideDuplicatePair } from '../../core/api/fn/references/decide-duplicate-pair';
import { deduplicationReport } from '../../core/api/fn/references/deduplication-report';
import { deduplicationReportCsv } from '../../core/api/fn/references/deduplication-report-csv';
import { getDedupSettings } from '../../core/api/fn/references/get-dedup-settings';
import { listDuplicatePairs } from '../../core/api/fn/references/list-duplicate-pairs';
import { putDedupSettings } from '../../core/api/fn/references/put-dedup-settings';
import { runDeduplication } from '../../core/api/fn/references/run-deduplication';
import { DuplicatePairOut } from '../../core/api/models/duplicate-pair-out';
import { DedupReportOut } from '../../core/api/models/dedup-report-out';
import { SearchReferenceOut } from '../../core/api/models/search-reference-out';
import { withJsonBody } from '../../core/errors/problem';
import { fileNameFrom, saveFile } from '../../shared/download';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

type Kind = 'certain' | 'probable' | 'related';
type Status = 'pending' | 'confirmed' | 'rejected';

/**
 * Deduplication (docs/modulos.md 7.2, lesson L4): every pair says why it was found and
 * shows the two records side by side. Nothing is removed without a person, and every
 * decision can be undone.
 */
@Component({
  selector: 'rm-duplicates-page',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatButtonToggleModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <a routerLink=".." class="back">← {{ 'searches.title' | transloco }}</a>
    <h2>
      {{ 'dedup.title' | transloco }}
      <span class="term" tabindex="0" [matTooltip]="'dedup.help' | transloco">?</span>
    </h2>
    <p class="muted">{{ 'dedup.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />

    @if (report(); as r) {
      <p>
        {{
          'dedup.summary'
            | transloco
              : { imported: r.imported, removed: r.duplicates_removed, left: r.after_duplicates }
        }}
      </p>
    }
    <div class="actions">
      @if (canDecide()) {
        <button mat-flat-button type="button" [disabled]="busy()" (click)="run()">
          {{ 'dedup.run' | transloco }}
        </button>
        @if ((report()?.pending?.['certain'] ?? 0) > 0) {
          <button mat-stroked-button type="button" [disabled]="busy()" (click)="confirmCertain()">
            {{ 'dedup.confirmCertain' | transloco: { count: report()!.pending['certain'] } }}
          </button>
        }
      }
      <button mat-stroked-button type="button" [disabled]="busy()" (click)="downloadCsv()">
        {{ 'dedup.csv' | transloco }}
      </button>
    </div>

    @if (context.isAdmin()) {
      <div class="row">
        <mat-form-field subscriptSizing="dynamic">
          <mat-label>{{ 'dedup.threshold' | transloco }}</mat-label>
          <input matInput type="number" min="0.8" max="1" step="0.01" [(ngModel)]="threshold" />
        </mat-form-field>
        <span class="term" tabindex="0" [matTooltip]="'dedup.thresholdHelp' | transloco">?</span>
        <button mat-stroked-button type="button" [disabled]="busy()" (click)="saveThreshold()">
          {{ 'dedup.saveThreshold' | transloco }}
        </button>
      </div>
    }

    <div class="row">
      <mat-button-toggle-group
        [(ngModel)]="kind"
        (ngModelChange)="load()"
        [hideSingleSelectionIndicator]="true"
      >
        @for (k of kinds; track k) {
          <mat-button-toggle [value]="k">
            {{ 'dedup.kind.' + k | transloco }} ({{ report()?.pending?.[k] ?? 0 }})
          </mat-button-toggle>
        }
      </mat-button-toggle-group>
      <mat-button-toggle-group
        [(ngModel)]="status"
        (ngModelChange)="load()"
        [hideSingleSelectionIndicator]="true"
      >
        @for (s of statuses; track s) {
          <mat-button-toggle [value]="s">{{ 'dedup.status.' + s | transloco }}</mat-button-toggle>
        }
      </mat-button-toggle-group>
    </div>
    <p class="muted">{{ 'dedup.kindHelp.' + kind | transloco }}</p>

    @if (!pairs().length) {
      <p class="muted">{{ 'dedup.empty' | transloco }}</p>
    }
    @for (pair of pairs(); track pair.id) {
      <mat-card class="block">
        <mat-card-content>
          <p>
            <span class="badge">{{ 'dedup.kind.' + pair.kind | transloco }}</span>
            {{ 'dedup.score' | transloco: { value: percent(pair.score) } }}
            @for (c of criteriaList(pair); track c) {
              <span class="badge">{{ c }}</span>
            }
          </p>
          <div class="side">
            @for (side of sides; track side) {
              <div class="record" [class.kept]="pair.kept_id === record(pair, side).id">
                <strong>{{ record(pair, side).title }}</strong>
                <div class="muted">
                  {{ record(pair, side).authors || '—' }} · {{ record(pair, side).year || '—' }}
                </div>
                <div class="muted">
                  {{ record(pair, side).journal || '—' }}
                  @if (record(pair, side).volume) {
                    · {{ 'dedup.volume' | transloco }} {{ record(pair, side).volume }}
                  }
                  @if (record(pair, side).pages) {
                    · {{ 'dedup.pages' | transloco }} {{ record(pair, side).pages }}
                  }
                </div>
                <div class="muted">
                  DOI {{ record(pair, side).doi || '—' }} · PMID
                  {{ record(pair, side).pmid || '—' }}
                </div>
                @if (pair.kept_id === record(pair, side).id) {
                  <span class="badge">{{ 'dedup.kept' | transloco }}</span>
                }
                @if (canDecide() && pair.status === 'pending' && pair.kind !== 'related') {
                  <button
                    mat-stroked-button
                    type="button"
                    [disabled]="busy()"
                    (click)="decide(pair, 'confirm', side)"
                  >
                    {{ 'dedup.keepThis' | transloco }}
                  </button>
                }
              </div>
            }
          </div>
          @if (canDecide()) {
            <div class="actions">
              @if (pair.status === 'pending' && pair.kind !== 'related') {
                <button
                  mat-button
                  type="button"
                  [disabled]="busy()"
                  (click)="decide(pair, 'reject')"
                >
                  {{ 'dedup.notDuplicate' | transloco }}
                </button>
              }
              @if (pair.status !== 'pending') {
                <button mat-button type="button" [disabled]="busy()" (click)="decide(pair, 'undo')">
                  {{ 'dedup.undo' | transloco }}
                </button>
              }
            </div>
          }
        </mat-card-content>
      </mat-card>
    }
  `,
  styles: `
    .side {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }
    .record {
      border: 1px solid var(--mat-sys-outline-variant, #ccc);
      border-radius: 8px;
      padding: 8px;
    }
    .record.kept {
      border-color: var(--mat-sys-primary, #2e7d32);
    }
  `,
})
export class DuplicatesPage implements OnInit {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  protected readonly context = inject(ProjectContext);

  protected readonly kinds: Kind[] = ['certain', 'probable', 'related'];
  protected readonly statuses: Status[] = ['pending', 'confirmed', 'rejected'];
  protected readonly sides = ['a', 'b'] as const;
  protected kind: Kind = 'certain';
  protected status: Status = 'pending';
  protected threshold = 0.95;

  protected readonly pairs = signal<DuplicatePairOut[]>([]);
  protected readonly report = signal<DedupReportOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly canDecide = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.includes('admin') || roles.includes('reviewer');
  });

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(async () => {
      const settings = await this.api.invoke(getDedupSettings, { project_id: this.projectId() });
      this.threshold = settings.title_threshold ?? 0.95;
      await this.refresh();
    });
  }

  protected record(pair: DuplicatePairOut, side: 'a' | 'b'): SearchReferenceOut {
    return side === 'a' ? pair.a : pair.b;
  }

  protected percent(score: number): string {
    return (score * 100).toFixed(1);
  }

  protected criteriaList(pair: DuplicatePairOut): string[] {
    const c = pair.criteria as Record<string, unknown>;
    const out: string[] = [];
    for (const key of ['same_doi', 'same_pmid', 'first_author', 'journal', 'volume', 'pages']) {
      if (c[key]) out.push(this.transloco.translate('dedup.criterion.' + key));
    }
    if (c['year'] === 'same') out.push(this.transloco.translate('dedup.criterion.year'));
    if (c['year'] === 'missing') out.push(this.transloco.translate('dedup.criterion.yearMissing'));
    if (c['differs_in_numbers']) out.push(this.transloco.translate('dedup.criterion.numbers'));
    const words = c['differs_in_words'] as string[] | undefined;
    if (words?.length) {
      out.push(this.transloco.translate('dedup.criterion.words', { words: words.join(', ') }));
    }
    return out;
  }

  async load(): Promise<void> {
    await this.guard(() => this.refresh());
  }

  private async refresh(): Promise<void> {
    const [pairs, report] = await Promise.all([
      this.api.invoke(listDuplicatePairs, {
        project_id: this.projectId(),
        kind: this.kind,
        status: this.status,
      }),
      this.api.invoke(deduplicationReport, { project_id: this.projectId() }),
    ]);
    this.pairs.set(pairs);
    this.report.set(report);
  }

  async run(): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(runDeduplication, { project_id: this.projectId() });
      await this.refresh();
    });
  }

  async confirmCertain(): Promise<void> {
    if (!window.confirm(this.transloco.translate('dedup.confirmCertainAsk'))) return;
    await this.guard(async () => {
      await this.api.invoke(confirmCertainDuplicates, { project_id: this.projectId() });
      await this.refresh();
    });
  }

  async decide(
    pair: DuplicatePairOut,
    action: 'confirm' | 'reject' | 'undo',
    keep?: 'a' | 'b',
  ): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(decideDuplicatePair, {
        project_id: this.projectId(),
        pair_id: pair.id,
        body: { action, keep: keep ?? null, version: pair.version },
      });
      await this.refresh();
    });
  }

  async saveThreshold(): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(putDedupSettings, {
        project_id: this.projectId(),
        body: { title_threshold: Number(this.threshold) },
      });
      await this.api.invoke(runDeduplication, { project_id: this.projectId() });
      await this.refresh();
    });
  }

  async downloadCsv(): Promise<void> {
    await this.guard(async () => {
      const response = await this.api.invoke$Response(deduplicationReportCsv, {
        project_id: this.projectId(),
      });
      const blob = new Blob([response.body as unknown as string], { type: 'text/csv' });
      saveFile(blob, fileNameFrom(response.headers.get('content-disposition'), 'deduplicacao.csv'));
    });
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
