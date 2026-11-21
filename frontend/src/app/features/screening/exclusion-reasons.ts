import { Component, OnInit, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { createExclusionReason } from '../../core/api/fn/screening/create-exclusion-reason';
import { deleteExclusionReason } from '../../core/api/fn/screening/delete-exclusion-reason';
import { listExclusionReasons } from '../../core/api/fn/screening/list-exclusion-reasons';
import { mergeExclusionReason } from '../../core/api/fn/screening/merge-exclusion-reason';
import { renameExclusionReason } from '../../core/api/fn/screening/rename-exclusion-reason';
import { ReasonOut } from '../../core/api/models/reason-out';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

/** The text of a reason: the label the group wrote, or the translation of a standard key. */
export function reasonText(r: ReasonOut, t: (key: string) => string): string {
  if (r.label) return r.label;
  return r.key ? t('screening.reasons.standard.' + r.key) : '';
}

/** Editable list of exclusion reasons (admin; lesson L5). */
@Component({
  selector: 'rm-exclusion-reasons',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <mat-card class="block">
      <mat-card-content>
        <h3>
          {{ 'screening.reasons.title' | transloco }}
          <span class="term" tabindex="0" [matTooltip]="'screening.reasons.help' | transloco"
            >?</span
          >
        </h3>
        <rm-form-error [error]="error()" />
        <ul class="item-list">
          @for (r of reasons(); track r.id) {
            <li>
              @if (editing === r.id) {
                <mat-form-field subscriptSizing="dynamic">
                  <mat-label>{{ 'screening.reasons.rename' | transloco }}</mat-label>
                  <input matInput maxlength="200" [(ngModel)]="draft" />
                </mat-form-field>
                <button mat-button type="button" [disabled]="busy()" (click)="rename(r)">
                  {{ 'screening.reasons.save' | transloco }}
                </button>
              } @else {
                <strong>{{ text(r) }}</strong>
                <span class="muted">
                  · {{ 'screening.reasons.uses' | transloco: { count: r.uses } }}</span
                >
                @if (r.merged_into_id) {
                  <span class="muted">
                    ·
                    {{
                      'screening.reasons.merged' | transloco: { name: nameOf(r.merged_into_id) }
                    }}</span
                  >
                } @else {
                  <button mat-button type="button" [disabled]="busy()" (click)="startRename(r)">
                    {{ 'screening.reasons.rename' | transloco }}
                  </button>
                  @if (r.uses === 0) {
                    <button mat-button type="button" [disabled]="busy()" (click)="remove(r)">
                      {{ 'screening.reasons.remove' | transloco }}
                    </button>
                  }
                  <mat-form-field subscriptSizing="dynamic" class="merge">
                    <mat-label>{{ 'screening.reasons.mergeInto' | transloco }}</mat-label>
                    <mat-select (selectionChange)="merge(r, $event.value)">
                      @for (o of active(); track o.id) {
                        @if (o.id !== r.id) {
                          <mat-option [value]="o.id">{{ text(o) }}</mat-option>
                        }
                      }
                    </mat-select>
                  </mat-form-field>
                }
              }
            </li>
          }
        </ul>
        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'screening.reasons.new' | transloco }}</mat-label>
            <input matInput maxlength="200" [(ngModel)]="newLabel" />
          </mat-form-field>
          <button
            mat-stroked-button
            type="button"
            [disabled]="busy() || newLabel.trim().length < 2"
            (click)="add()"
          >
            {{ 'screening.reasons.add' | transloco }}
          </button>
        </div>
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .merge {
      width: 220px;
    }
  `,
})
export class ExclusionReasons implements OnInit {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly context = inject(ProjectContext);
  readonly changed = output<void>();

  protected readonly reasons = signal<ReasonOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected editing: string | null = null;
  protected draft = '';
  protected newLabel = '';

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(() => this.load());
  }

  private async load(): Promise<void> {
    this.reasons.set(await this.api.invoke(listExclusionReasons, { project_id: this.projectId() }));
  }

  protected active(): ReasonOut[] {
    return this.reasons().filter((r) => !r.merged_into_id);
  }

  protected text(r: ReasonOut): string {
    return reasonText(r, (k) => this.transloco.translate(k));
  }

  protected nameOf(id: string): string {
    const r = this.reasons().find((x) => x.id === id);
    return r ? this.text(r) : '';
  }

  protected startRename(r: ReasonOut): void {
    this.editing = r.id;
    this.draft = this.text(r);
  }

  async rename(r: ReasonOut): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(renameExclusionReason, {
        project_id: this.projectId(),
        reason_id: r.id,
        body: { label: this.draft.trim(), version: r.version },
      });
      this.editing = null;
      await this.load();
      this.changed.emit();
    });
  }

  async add(): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(createExclusionReason, {
        project_id: this.projectId(),
        body: { label: this.newLabel.trim() },
      });
      this.newLabel = '';
      await this.load();
      this.changed.emit();
    });
  }

  async remove(r: ReasonOut): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(deleteExclusionReason, {
        project_id: this.projectId(),
        reason_id: r.id,
      });
      await this.load();
      this.changed.emit();
    });
  }

  async merge(r: ReasonOut, intoId: string): Promise<void> {
    const ask = this.transloco.translate('screening.reasons.mergeAsk', {
      from: this.text(r),
      to: this.nameOf(intoId),
    });
    if (!window.confirm(ask)) {
      await this.load();
      return;
    }
    await this.guard(async () => {
      await this.api.invoke(mergeExclusionReason, {
        project_id: this.projectId(),
        reason_id: r.id,
        body: { into_id: intoId, version: r.version },
      });
      await this.load();
      this.changed.emit();
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
