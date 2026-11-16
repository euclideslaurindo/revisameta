import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { discardRobImport } from '../../core/api/fn/risk-of-bias/discard-rob-import';
import { lockRob } from '../../core/api/fn/risk-of-bias/lock-rob';
import { reopenRobConsensus } from '../../core/api/fn/risk-of-bias/reopen-rob-consensus';
import { robReview } from '../../core/api/fn/risk-of-bias/rob-review';
import { unlockRob } from '../../core/api/fn/risk-of-bias/unlock-rob';
import { RobReviewOut } from '../../core/api/models/rob-review-out';
import { TargetState } from '../../core/api/models/target-state';
import { FormError } from '../../shared/form-error';
import { LocalDatePipe } from '../../shared/local-date.pipe';
import { ProjectContext } from '../project/project-context';
import { localized } from './rob-tool-editor';

/**
 * Before locking the risk-of-bias stage: where every study stands. The stage locks
 * only with every study finished; unlocking, reopening a consensus and discarding an
 * import need a justification, kept in the stage history.
 */
@Component({
  selector: 'rm-rob-review-page',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
    LocalDatePipe,
  ],
  template: `
    <a [routerLink]="['/projetos', projectId(), 'risco-de-vies']"
      >← {{ 'rob.table.back' | transloco }}</a
    >
    <h2>{{ 'rob.review.title' | transloco }}</h2>
    <p class="muted">{{ 'rob.review.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />

    @if (data(); as r) {
      <mat-card class="block">
        <mat-card-content>
          <p>{{ 'rob.review.progress' | transloco: { ready: r.ready, total: r.total } }}</p>
          @if (r.locked) {
            <p class="notice">{{ 'rob.review.locked' | transloco }}</p>
            @if (isAdmin()) {
              <div class="row">
                <mat-form-field subscriptSizing="dynamic" class="wide">
                  <mat-label>{{ 'rob.review.unlockReason' | transloco }}</mat-label>
                  <input matInput [(ngModel)]="reason" maxlength="1000" />
                </mat-form-field>
                <button
                  mat-stroked-button
                  type="button"
                  [disabled]="busy() || reason.trim().length < 5"
                  (click)="unlock()"
                >
                  {{ 'rob.review.unlock' | transloco }}
                </button>
              </div>
            }
          } @else if (isAdmin()) {
            <button
              mat-flat-button
              type="button"
              [disabled]="busy() || !r.can_lock"
              (click)="lock()"
            >
              {{ 'rob.review.lock' | transloco }}
            </button>
            @if (!r.can_lock) {
              <p class="muted">{{ 'rob.review.lockHint' | transloco }}</p>
            }
          }
        </mat-card-content>
      </mat-card>

      <ul class="item-list">
        @for (s of r.studies; track s.study_id) {
          <li class="stack-item">
            <div>
              <a [routerLink]="['/projetos', projectId(), 'estudos', s.study_id]"
                ><strong>{{ s.label }}</strong></a
              >
              <span class="badge" [class.badge-block]="s.state !== 'ready'">
                {{ 'rob.review.state.' + s.state | transloco }}
              </span>
              @if (s.tool_key) {
                <span class="muted"> · {{ toolName(s.tool_name) }} ({{ s.tool_version }})</span>
              }
              @for (t of s.targets; track $index) {
                <div class="muted">
                  @if (t.timepoint) {
                    {{ t.outcome_name }} · {{ t.timepoint }}:
                  }
                  {{ 'rob.review.target.' + t.state | transloco }}
                  @if (t.final_kind === 'imported') {
                    <span class="badge">{{ 'rob.table.imported' | transloco }}</span>
                  }
                  @if (t.final_id && isAdmin() && !r.locked) {
                    @if (acting() === t.final_id) {
                      <div class="row">
                        <mat-form-field subscriptSizing="dynamic" class="wide">
                          <mat-label>{{ 'rob.review.why' | transloco }}</mat-label>
                          <input matInput [(ngModel)]="reason" maxlength="1000" />
                        </mat-form-field>
                        <button
                          mat-stroked-button
                          type="button"
                          [disabled]="busy() || reason.trim().length < 5"
                          (click)="act(t)"
                        >
                          {{ 'common.confirm' | transloco }}
                        </button>
                      </div>
                    } @else {
                      <button
                        mat-button
                        type="button"
                        (click)="acting.set(t.final_id); reason = ''"
                      >
                        {{
                          (t.final_kind === 'imported' ? 'rob.review.discard' : 'rob.review.reopen')
                            | transloco
                        }}
                      </button>
                    }
                  }
                </div>
              }
            </div>
          </li>
        }
      </ul>

      @if (r.history.length) {
        <h3>{{ 'rob.review.history' | transloco }}</h3>
        <ul class="item-list">
          @for (e of r.history; track $index) {
            <li>
              <div>
                <strong>{{ 'rob.review.action.' + e.action | transloco }}</strong>
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
export class RobReviewPage implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly projectId = computed(() => this.context.project()!.id);
  protected readonly isAdmin = computed(() => this.context.isAdmin());
  protected readonly data = signal<RobReviewOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly acting = signal<string | null>(null);
  protected reason = '';
  private readonly lang = toSignal(inject(TranslocoService).langChanges$, {
    initialValue: 'pt-BR',
  });

  protected toolName(name: Record<string, string> | null | undefined): string {
    return name ? localized(name, this.lang()) : '';
  }

  async ngOnInit(): Promise<void> {
    await this.run(() => this.api.invoke(robReview, { project_id: this.projectId() }));
  }

  async lock(): Promise<void> {
    await this.run(() => this.api.invoke(lockRob, { project_id: this.projectId() }));
  }

  async unlock(): Promise<void> {
    await this.run(() =>
      this.api.invoke(unlockRob, {
        project_id: this.projectId(),
        body: { justification: this.reason.trim() },
      }),
    );
  }

  async act(target: TargetState): Promise<void> {
    const params = {
      project_id: this.projectId(),
      assessment_id: target.final_id!,
      body: { justification: this.reason.trim() },
    };
    await this.run(() =>
      target.final_kind === 'imported'
        ? this.api.invoke(discardRobImport, params)
        : this.api.invoke(reopenRobConsensus, params),
    );
  }

  private async run(action: () => Promise<RobReviewOut>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.data.set(await action());
      this.reason = '';
      this.acting.set(null);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
