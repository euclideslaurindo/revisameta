import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { LocalDatePipe } from '../../shared/local-date.pipe';
import { Api } from '../../core/api/api';
import { extractionReview } from '../../core/api/fn/extraction/extraction-review';
import { lockExtraction } from '../../core/api/fn/extraction/lock-extraction';
import { reopenConsensus } from '../../core/api/fn/extraction/reopen-consensus';
import { unlockExtraction } from '../../core/api/fn/extraction/unlock-extraction';
import { FinalReviewOut } from '../../core/api/models/final-review-out';
import { ItemOut } from '../../core/api/models/item-out';
import { NumberCheck } from '../../core/api/models/number-check';
import { ReviewStudy } from '../../core/api/models/review-study';
import { FormError } from '../../shared/form-error';
import { displayDecimal, displayParams } from '../../shared/numbers';
import { ProjectContext } from '../project/project-context';
import { fieldLabel } from './comparison-format';

/**
 * Block F: before locking the extraction, every number of the consensus with its
 * origin, who extracted it and how it was checked. Locking freezes the stage;
 * unlocking and reopening a consensus need a justification.
 */
@Component({
  selector: 'rm-review-page',
  imports: [
    LocalDatePipe,
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <p class="muted">{{ 'review.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />
    @if (data(); as r) {
      <mat-card class="block">
        <mat-card-content>
          @if (r.locked) {
            <p class="notice">{{ 'review.locked' | transloco }}</p>
            @if (isAdmin()) {
              <div class="row">
                <mat-form-field subscriptSizing="dynamic" class="wide">
                  <mat-label>{{ 'review.unlockReason' | transloco }}</mat-label>
                  <input matInput [(ngModel)]="unlockReason" />
                </mat-form-field>
                <button mat-stroked-button type="button" [disabled]="busy()" (click)="unlock()">
                  {{ 'review.unlock' | transloco }}
                </button>
              </div>
            }
          } @else {
            <p>{{ 'review.readyCount' | transloco: { ready: r.ready, total: r.total } }}</p>
            @if (isAdmin()) {
              <button
                mat-flat-button
                type="button"
                [disabled]="busy() || !r.can_lock"
                (click)="lock()"
              >
                {{ 'review.lock' | transloco }}
              </button>
              @if (!r.can_lock) {
                <p class="muted">{{ 'review.lockHint' | transloco }}</p>
              }
            }
          }
        </mat-card-content>
      </mat-card>

      @if (r.total === 0) {
        <p class="empty">{{ 'review.empty' | transloco }}</p>
      }

      @for (s of r.studies; track s.study_id) {
        <mat-card class="block review-study">
          <mat-card-header>
            <mat-card-title>
              <h3>
                {{ s.label }}
                <span class="badge" [class.badge-block]="s.blockers.length > 0">
                  {{ (s.blockers.length ? 'review.pending' : 'review.ready') | transloco }}
                </span>
              </h3>
            </mat-card-title>
          </mat-card-header>
          <mat-card-content>
            @for (b of s.blockers; track b) {
              <div class="alert-item" [class.alert-block]="true">
                {{ b | transloco: { count: s.open_alerts.length } }}
              </div>
            }
            @for (a of s.open_alerts; track a.id) {
              <div class="alert-item">{{ a.code | transloco: params(a.params) }}</div>
            }
            <p class="muted">
              {{ 'review.extractedBy' | transloco: { names: s.extractors.join(', ') || '—' } }}
              @if (s.checked_by) {
                · {{ 'review.checkedBy' | transloco: { name: s.checked_by } }} ({{
                  s.checked_at | localDate: 'short'
                }})
              }
              @if (s.justified_alerts) {
                · {{ 'review.justified' | transloco: { count: s.justified_alerts } }}
              }
            </p>
            <div class="actions">
              @if (s.consensus_id) {
                <a
                  mat-stroked-button
                  [routerLink]="['/projetos', projectId(), 'extracoes', s.consensus_id]"
                >
                  {{ 'consensus.open' | transloco }}
                </a>
              }
              @if (isAdmin()) {
                <a
                  mat-button
                  [routerLink]="['/projetos', projectId(), 'estudos', s.study_id, 'consenso']"
                >
                  {{ 'consensus.link' | transloco }}
                </a>
              }
            </div>

            @if (s.arms.length) {
              <div class="review-table" role="table">
                <div class="review-head" role="row">
                  <span role="columnheader">{{ 'review.group' | transloco }}</span>
                  <span role="columnheader">{{ 'review.numbers' | transloco }}</span>
                  <span role="columnheader">{{ 'review.origin' | transloco }}</span>
                </div>
                @for (a of s.arms; track a.arm_label) {
                  <div class="review-row" role="row">
                    <span role="cell"
                      >{{ a.arm_label
                      }}<span class="muted">{{
                        a.group_label ? ' · ' + a.group_label : ''
                      }}</span></span
                    >
                    <span role="cell">
                      n = {{ a.n ?? '—' }}
                      <span class="check" [class.check-warn]="warn(a.check)">{{
                        checkText(a.check)
                      }}</span>
                    </span>
                    <span role="cell" class="muted">—</span>
                  </div>
                }
                @for (row of s.rows; track $index) {
                  <div class="review-row" role="row">
                    <span role="cell">
                      {{ row.outcome_name }} · {{ row.timepoint }}<br />
                      {{ row.arm_label
                      }}<span class="muted">{{
                        row.group_label ? ' · ' + row.group_label : ''
                      }}</span
                      ><br />
                      <span class="muted">
                        {{ 'extraction.data.' + row.value_type | transloco }}
                        @if (row.dispersion_type) {
                          · {{ 'extraction.dispersion.' + row.dispersion_type | transloco }}
                        }
                      </span>
                    </span>
                    <span role="cell">
                      @for (n of row.numbers; track n.field) {
                        <div>
                          {{ label(n.field) }} = <strong>{{ num(n.value) }}</strong>
                          <span class="check" [class.check-warn]="warn(n.check)">{{
                            checkText(n.check)
                          }}</span>
                        </div>
                      }
                    </span>
                    <span role="cell">
                      {{ row.source_location || ('consensus.noSource' | transloco) }}
                      @if (row.dispersion_source) {
                        <div class="muted">
                          {{ 'extraction.data.dispersionSource' | transloco }}:
                          {{ row.dispersion_source }}
                        </div>
                      }
                      @if (row.has_annotation) {
                        <div class="muted">{{ 'consensus.markedPassage' | transloco }}</div>
                      }
                    </span>
                  </div>
                }
              </div>
            }

            @if (isAdmin() && s.consensus_status === 'submitted' && !r.locked) {
              @if (reopening() === s.study_id) {
                <div class="row">
                  <mat-form-field subscriptSizing="dynamic" class="wide">
                    <mat-label>{{ 'review.reopenReason' | transloco }}</mat-label>
                    <input matInput [(ngModel)]="reopenReason" />
                  </mat-form-field>
                  <button mat-stroked-button type="button" [disabled]="busy()" (click)="reopen(s)">
                    {{ 'common.confirm' | transloco }}
                  </button>
                </div>
              } @else {
                <button mat-button type="button" (click)="reopening.set(s.study_id)">
                  {{ 'review.reopen' | transloco }}
                </button>
              }
            }
          </mat-card-content>
        </mat-card>
      }

      @if (r.history.length) {
        <h3>{{ 'review.history' | transloco }}</h3>
        <ul class="item-list">
          @for (e of r.history; track $index) {
            <li>
              <div>
                <strong>{{ 'review.action.' + e.action | transloco }}</strong>
                · {{ e.user_name }} · {{ e.created_at | localDate: 'short' }}
                @if (e.justification) {
                  <div class="muted">{{ e.justification }}</div>
                }
              </div>
            </li>
          }
        </ul>
      }
    }
  `,
})
export class ReviewPage implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: 'pt-BR' });

  protected readonly data = signal<FinalReviewOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly reopening = signal<string | null>(null);
  protected readonly isAdmin = computed(() =>
    (this.context.project()?.my_roles ?? []).includes('admin'),
  );
  protected unlockReason = '';
  protected reopenReason = '';

  private t = (key: string, params?: Record<string, unknown>) => {
    this.lang();
    return this.transloco.translate(key, params);
  };

  protected projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.run(() => this.api.invoke(extractionReview, { project_id: this.projectId() }));
  }

  protected label(field: string): string {
    return fieldLabel({ section: 'row', field } as ItemOut, this.t);
  }

  protected num(value: string): string {
    return displayDecimal(value, this.lang());
  }

  protected params(params: Record<string, unknown>): Record<string, unknown> {
    return displayParams(params, this.lang());
  }

  protected warn(check: NumberCheck): boolean {
    return check.status === 'edited' || check.status === 'undecided';
  }

  protected checkText(check: NumberCheck): string {
    const params = {
      name: check.by ?? '—',
      side: check.choice ? this.t('review.side.' + check.choice) : '',
    };
    return this.t('review.check.' + check.status, params);
  }

  private async run(action: () => Promise<FinalReviewOut>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.data.set(await action());
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }

  async lock(): Promise<void> {
    await this.run(() => this.api.invoke(lockExtraction, { project_id: this.projectId() }));
  }

  async unlock(): Promise<void> {
    await this.run(() =>
      this.api.invoke(unlockExtraction, {
        project_id: this.projectId(),
        body: { justification: this.unlockReason },
      }),
    );
    if (!this.error()) this.unlockReason = '';
  }

  async reopen(study: ReviewStudy): Promise<void> {
    const project_id = this.projectId();
    await this.run(async () => {
      await this.api.invoke(reopenConsensus, {
        project_id,
        extraction_id: study.consensus_id!,
        body: { justification: this.reopenReason },
      });
      return this.api.invoke(extractionReview, { project_id });
    });
    if (!this.error()) {
      this.reopening.set(null);
      this.reopenReason = '';
    }
  }
}
