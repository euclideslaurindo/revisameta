import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { TranslocoPipe } from '@jsverse/transloco';

export interface ConfirmData {
  /** i18n key of the message. */
  message: string;
  params?: Record<string, unknown>;
  confirmLabel?: string;
}

/** Destructive actions always ask first (docs/modulos.md, 12). */
@Component({
  selector: 'rm-confirm-dialog',
  imports: [MatButtonModule, MatDialogModule, TranslocoPipe],
  template: `
    <mat-dialog-content>{{ data.message | transloco: data.params ?? {} }}</mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" [mat-dialog-close]="false">{{ 'common.cancel' | transloco }}</button>
      <button mat-flat-button type="button" [mat-dialog-close]="true">
        {{ data.confirmLabel ?? 'common.confirm' | transloco }}
      </button>
    </mat-dialog-actions>
  `,
})
export class ConfirmDialog {
  protected readonly data = inject<ConfirmData>(MAT_DIALOG_DATA);
}
