import { Component, OnInit, inject, input, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { verifyEmail } from '../../core/api/fn/auth/verify-email';
import { FormError } from '../../shared/form-error';

@Component({
  selector: 'rm-verify-email-page',
  imports: [TranslocoPipe, MatCardModule, MatProgressBarModule, FormError],
  template: `
    <mat-card class="auth-card">
      <mat-card-header>
        <mat-card-title
          ><h1>{{ 'verify.title' | transloco }}</h1></mat-card-title
        >
      </mat-card-header>
      <mat-card-content>
        @if (!token()) {
          <div class="notice notice-error" role="alert">
            {{ 'verify.missingToken' | transloco }}
          </div>
        } @else if (error()) {
          <rm-form-error [error]="error()" />
        } @else {
          <p role="status">{{ 'verify.working' | transloco }}</p>
          <mat-progress-bar mode="indeterminate" />
        }
      </mat-card-content>
    </mat-card>
  `,
})
export class VerifyEmailPage implements OnInit {
  private readonly api = inject(Api);
  private readonly router = inject(Router);

  readonly token = input<string>();
  protected readonly error = signal<unknown>(null);

  async ngOnInit(): Promise<void> {
    const token = this.token();
    if (!token) return;
    try {
      await this.api.invoke(verifyEmail, { body: { token } });
      await this.router.navigate(['/entrar'], { queryParams: { verificado: '1' } });
    } catch (error) {
      this.error.set(error);
    }
  }
}
