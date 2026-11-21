import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { listMembers } from '../../core/api/fn/projects/list-members';
import { assignBatch } from '../../core/api/fn/screening/assign-batch';
import { getScreeningSettings } from '../../core/api/fn/screening/get-screening-settings';
import { listAssignments } from '../../core/api/fn/screening/list-assignments';
import { putScreeningSettings } from '../../core/api/fn/screening/put-screening-settings';
import { resolveConflict } from '../../core/api/fn/screening/resolve-conflict';
import { screeningAgreement } from '../../core/api/fn/screening/screening-agreement';
import { takeBackBatch } from '../../core/api/fn/screening/take-back-batch';
import { MemberOut } from '../../core/api/models/member-out';
import { ScreeningAgreementOut } from '../../core/api/models/screening-agreement-out';
import { ScreeningAssignmentSummary } from '../../core/api/models/screening-assignment-summary';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

/** Admin tools of the screening: keywords, blinding, batches and agreement (kappa). */
@Component({
  selector: 'rm-screening-admin',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCheckboxModule,
    MatExpansionModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <h3>{{ 'screening.admin.title' | transloco }}</h3>
    <rm-form-error [error]="error()" />
    <mat-accordion>
      <mat-expansion-panel>
        <mat-expansion-panel-header>
          <mat-panel-title>{{ 'screening.admin.settings' | transloco }}</mat-panel-title>
        </mat-expansion-panel-header>
        <mat-form-field class="full">
          <mat-label>{{ 'screening.admin.includeKw' | transloco }}</mat-label>
          <textarea matInput rows="2" [(ngModel)]="includeKw"></textarea>
          <mat-hint>{{ 'screening.admin.kwHint' | transloco }}</mat-hint>
        </mat-form-field>
        <mat-form-field class="full">
          <mat-label>{{ 'screening.admin.excludeKw' | transloco }}</mat-label>
          <textarea matInput rows="2" [(ngModel)]="excludeKw"></textarea>
        </mat-form-field>
        <mat-checkbox [(ngModel)]="blind">{{ 'screening.admin.blind' | transloco }}</mat-checkbox>
        <span class="term" tabindex="0" [matTooltip]="'screening.admin.blindHelp' | transloco"
          >?</span
        >
        <div class="actions">
          <button mat-flat-button type="button" [disabled]="busy()" (click)="saveSettings()">
            {{ 'screening.admin.save' | transloco }}
          </button>
        </div>
      </mat-expansion-panel>

      <mat-expansion-panel (opened)="loadBatches()">
        <mat-expansion-panel-header>
          <mat-panel-title>{{ 'screening.admin.batches' | transloco }}</mat-panel-title>
        </mat-expansion-panel-header>
        <p class="muted">{{ 'screening.admin.batchesHelp' | transloco }}</p>
        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'screening.admin.reviewer' | transloco }}</mat-label>
            <mat-select [(ngModel)]="batchUser">
              @for (m of reviewers(); track m.user_id) {
                <mat-option [value]="m.user_id">{{ m.name }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'screening.admin.count' | transloco }}</mat-label>
            <input matInput type="number" min="1" max="5000" [(ngModel)]="batchCount" />
          </mat-form-field>
          <button
            mat-stroked-button
            type="button"
            [disabled]="busy() || !batchUser"
            (click)="assign()"
          >
            {{ 'screening.admin.assign' | transloco }}
          </button>
        </div>
        <ul class="item-list">
          @for (b of batches(); track b.user_id) {
            <li>
              {{ b.user_name }}:
              {{
                'screening.admin.batchLine'
                  | transloco: { assigned: b.assigned, decided: b.decided }
              }}
              <button mat-button type="button" [disabled]="busy()" (click)="takeBack(b)">
                {{ 'screening.admin.takeBack' | transloco }}
              </button>
            </li>
          }
        </ul>
      </mat-expansion-panel>

      <mat-expansion-panel (opened)="loadAgreement()">
        <mat-expansion-panel-header>
          <mat-panel-title>{{ 'screening.admin.agreement' | transloco }}</mat-panel-title>
        </mat-expansion-panel-header>
        <p class="muted">{{ 'screening.admin.kappaHelp' | transloco }}</p>
        @if (!agreement().length) {
          <p class="muted">{{ 'screening.admin.noAgreement' | transloco }}</p>
        }
        @for (a of agreement(); track a.user_a + a.user_b) {
          <p>
            {{ a.name_a }} × {{ a.name_b }}:
            {{
              'screening.admin.kappaLine'
                | transloco
                  : { items: a.items, percent: fmt(a.agreement_percent, 1), kappa: fmt(a.kappa, 2) }
            }}
            @if (a.kappa !== null && a.kappa !== undefined) {
              — {{ kappaWords(a.kappa) }}
            }
          </p>
        }
      </mat-expansion-panel>
    </mat-accordion>
  `,
  styles: `
    .full {
      width: 100%;
    }
  `,
})
export class ScreeningAdmin implements OnInit {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly context = inject(ProjectContext);
  readonly changed = output<void>();

  protected includeKw = '';
  protected excludeKw = '';
  protected blind = true;
  protected batchUser: string | null = null;
  protected batchCount = 100;
  protected readonly reviewers = signal<MemberOut[]>([]);
  protected readonly batches = signal<ScreeningAssignmentSummary[]>([]);
  protected readonly agreement = signal<ScreeningAgreementOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(async () => {
      const s = await this.api.invoke(getScreeningSettings, { project_id: this.projectId() });
      this.includeKw = (s.include_keywords ?? []).join('; ');
      this.excludeKw = (s.exclude_keywords ?? []).join('; ');
      this.blind = s.blind ?? true;
    });
  }

  private split(text: string): string[] {
    return text
      .split(/[;\n]/)
      .map((k) => k.trim())
      .filter((k) => k);
  }

  async saveSettings(): Promise<void> {
    if (!this.blind && !window.confirm(this.transloco.translate('screening.admin.revealAsk'))) {
      return;
    }
    await this.guard(async () => {
      await this.api.invoke(putScreeningSettings, {
        project_id: this.projectId(),
        body: {
          include_keywords: this.split(this.includeKw),
          exclude_keywords: this.split(this.excludeKw),
          blind: this.blind,
        },
      });
      this.changed.emit();
    });
  }

  async loadBatches(): Promise<void> {
    await this.guard(async () => {
      const members = await this.api.invoke(listMembers, { project_id: this.projectId() });
      this.reviewers.set(
        members.filter((m) => m.roles.includes('reviewer') || m.roles.includes('admin')),
      );
      this.batches.set(await this.api.invoke(listAssignments, { project_id: this.projectId() }));
    });
  }

  async assign(): Promise<void> {
    if (!this.batchUser) return;
    await this.guard(async () => {
      await this.api.invoke(assignBatch, {
        project_id: this.projectId(),
        body: { user_id: this.batchUser!, count: Number(this.batchCount) },
      });
      this.batches.set(await this.api.invoke(listAssignments, { project_id: this.projectId() }));
      this.changed.emit();
    });
  }

  async takeBack(b: ScreeningAssignmentSummary): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(takeBackBatch, { project_id: this.projectId(), user_id: b.user_id });
      this.batches.set(await this.api.invoke(listAssignments, { project_id: this.projectId() }));
      this.changed.emit();
    });
  }

  async loadAgreement(): Promise<void> {
    await this.guard(async () => {
      this.agreement.set(
        await this.api.invoke(screeningAgreement, { project_id: this.projectId() }),
      );
    });
  }

  protected fmt(value: number | null | undefined, digits: number): string {
    if (value === null || value === undefined) return '—';
    return value.toLocaleString(this.transloco.getActiveLang(), {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  /** Landis and Koch bands, only as a reading aid. */
  protected kappaWords(kappa: number): string {
    const band =
      kappa < 0
        ? 'poor'
        : kappa <= 0.2
          ? 'slight'
          : kappa <= 0.4
            ? 'fair'
            : kappa <= 0.6
              ? 'moderate'
              : kappa <= 0.8
                ? 'substantial'
                : 'almost';
    return this.transloco.translate('screening.admin.kappaBand.' + band);
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

/** Resolution of a conflict by the admin, with the reason. */
@Component({
  selector: 'rm-screening-admin-resolve',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
  ],
  template: `
    <mat-card class="block">
      <mat-card-content>
        <h4>{{ 'screening.admin.resolve' | transloco }}</h4>
        <rm-form-error [error]="error()" />
        <mat-form-field class="full">
          <mat-label>{{ 'screening.admin.reason' | transloco }}</mat-label>
          <input matInput maxlength="1000" [(ngModel)]="reason" />
        </mat-form-field>
        <div class="actions">
          <button
            mat-flat-button
            type="button"
            [disabled]="busy() || reason.trim().length < 3"
            (click)="resolve('include')"
          >
            {{ 'screening.admin.resolveInclude' | transloco }}
          </button>
          <button
            mat-stroked-button
            type="button"
            [disabled]="busy() || reason.trim().length < 3"
            (click)="resolve('exclude')"
          >
            {{ 'screening.admin.resolveExclude' | transloco }}
          </button>
        </div>
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .full {
      width: 100%;
    }
  `,
})
export class ScreeningAdminResolve {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  readonly referenceId = input.required<string>();
  readonly resolved = output<void>();
  protected reason = '';
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  async resolve(decision: 'include' | 'exclude'): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.invoke(resolveConflict, {
        project_id: this.context.project()!.id,
        reference_id: this.referenceId(),
        body: { decision, reason: this.reason.trim() },
      });
      this.reason = '';
      this.resolved.emit();
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }
}
