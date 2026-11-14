import { Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';
import { toSignal } from '@angular/core/rxjs-interop';

import { Api } from '../../core/api/api';
import { justifyAlert } from '../../core/api/fn/extraction/justify-alert';
import { AlertOut } from '../../core/api/models/alert-out';
import { FormError } from '../../shared/form-error';
import { displayParams } from '../../shared/numbers';

/** One safeguard alert: the explanation, and (when allowed) a short justification. */
@Component({
  selector: 'rm-alert-message',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
  ],
  template: `
    <div
      class="alert-item"
      [class.alert-block]="alert().severity === 'block'"
      [class.alert-justified]="current().status === 'justified'"
    >
      <span class="alert-tag">{{
        'extraction.alertSeverity.' + alert().severity | transloco
      }}</span>
      {{ alert().code | transloco: params(alert().params) }}
      @if (current().status === 'justified') {
        <div class="muted">
          {{ 'extraction.justified' | transloco }}: {{ current().justification }}
        </div>
      } @else if (canJustify() && alert().code !== 'extraction.alert.direction_unconfirmed') {
        @if (open()) {
          <div class="row">
            <mat-form-field subscriptSizing="dynamic" class="wide">
              <mat-label>{{ 'extraction.justification' | transloco }}</mat-label>
              <input matInput [(ngModel)]="text" />
            </mat-form-field>
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="justify()">
              {{ 'extraction.confirmValue' | transloco }}
            </button>
          </div>
          <rm-form-error [error]="error()" />
        } @else {
          <button mat-button type="button" (click)="open.set(true)">
            {{ 'extraction.valueIsCorrect' | transloco }}
          </button>
        }
      }
    </div>
  `,
})
export class AlertMessage {
  private readonly api = inject(Api);
  private readonly lang = toSignal(inject(TranslocoService).langChanges$, {
    initialValue: 'pt-BR',
  });

  protected params(params: Record<string, unknown> | null | undefined): Record<string, unknown> {
    return displayParams(params, this.lang());
  }

  readonly projectId = input.required<string>();
  readonly alert = input.required<AlertOut>();
  readonly canJustify = input(false);

  protected readonly open = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly justified = signal<AlertOut | null>(null);
  protected text = '';

  protected current(): AlertOut {
    return this.justified() ?? this.alert();
  }

  async justify(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.justified.set(
        await this.api.invoke(justifyAlert, {
          project_id: this.projectId(),
          alert_id: this.alert().id,
          body: { justification: this.text },
        }),
      );
      this.open.set(false);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
