import { Component, OnInit, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { Router } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { acceptInvitation } from '../../core/api/fn/projects/accept-invitation';
import { previewInvitation } from '../../core/api/fn/projects/preview-invitation';
import { InvitationPreview } from '../../core/api/models/invitation-preview';
import { FormError } from '../../shared/form-error';

@Component({
  selector: 'rm-invitation-page',
  imports: [TranslocoPipe, MatButtonModule, MatCardModule, FormError],
  template: `
    <mat-card class="auth-card">
      <mat-card-header>
        <mat-card-title
          ><h1>{{ 'invitation.title' | transloco }}</h1></mat-card-title
        >
      </mat-card-header>
      <mat-card-content>
        @if (error()) {
          <rm-form-error [error]="error()" />
        } @else if (preview(); as p) {
          <p>
            {{ 'invitation.text' | transloco: { project: p.project_title, roles: roleNames(p) } }}
          </p>
          <button mat-flat-button type="button" [disabled]="busy()" (click)="accept()">
            {{ 'invitation.accept' | transloco }}
          </button>
        } @else {
          <p role="status">{{ 'invitation.loading' | transloco }}</p>
        }
      </mat-card-content>
    </mat-card>
  `,
})
export class InvitationPage implements OnInit {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  private readonly transloco = inject(TranslocoService);

  readonly token = input.required<string>();
  protected readonly preview = signal<InvitationPreview | null>(null);
  protected readonly error = signal<unknown>(null);
  protected readonly busy = signal(false);

  async ngOnInit(): Promise<void> {
    try {
      this.preview.set(await this.api.invoke(previewInvitation, { token: this.token() }));
    } catch (error) {
      this.error.set(error);
    }
  }

  protected roleNames(preview: InvitationPreview): string {
    return preview.roles.map((role) => this.transloco.translate(`roles.${role}`)).join(', ');
  }

  async accept(): Promise<void> {
    this.busy.set(true);
    try {
      await this.api.invoke(acceptInvitation, { token: this.token() });
      await this.router.navigateByUrl('/projetos');
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
