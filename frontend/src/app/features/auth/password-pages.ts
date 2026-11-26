import { Component, inject, input, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { changePassword } from '../../core/api/fn/auth/change-password';
import { forgotPassword } from '../../core/api/fn/auth/forgot-password';
import { resetPassword } from '../../core/api/fn/auth/reset-password';
import { AuthService } from '../../core/auth/auth';
import { FormError } from '../../shared/form-error';

const MATERIAL = [MatButtonModule, MatCardModule, MatFormFieldModule, MatInputModule];

/** "Forgot my password": asks for the e-mail and sends a one-hour link. */
@Component({
  selector: 'rm-forgot-password-page',
  imports: [ReactiveFormsModule, RouterLink, TranslocoPipe, FormError, ...MATERIAL],
  template: `
    <mat-card class="auth-card">
      <mat-card-header>
        <mat-card-title
          ><h1>{{ 'password.forgotTitle' | transloco }}</h1></mat-card-title
        >
      </mat-card-header>
      <mat-card-content>
        @if (sent()) {
          <p class="notice notice-ok" role="status">{{ 'password.sent' | transloco }}</p>
        } @else {
          <p class="muted">{{ 'password.forgotHelp' | transloco }}</p>
          <form [formGroup]="form" (ngSubmit)="submit()" class="stack">
            <mat-form-field>
              <mat-label>{{ 'common.email' | transloco }}</mat-label>
              <input matInput type="email" formControlName="email" autocomplete="email" />
            </mat-form-field>
            <rm-form-error [error]="error()" />
            <button mat-flat-button type="submit" [disabled]="busy()">
              {{ 'password.send' | transloco }}
            </button>
          </form>
        }
        <p class="muted">
          <a routerLink="/entrar">{{ 'password.backToLogin' | transloco }}</a>
        </p>
      </mat-card-content>
    </mat-card>
  `,
})
export class ForgotPasswordPage {
  private readonly api = inject(Api);
  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
  });
  protected readonly busy = signal(false);
  protected readonly sent = signal(false);
  protected readonly error = signal<unknown>(null);

  async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.invoke(forgotPassword, { body: this.form.getRawValue() });
      this.sent.set(true);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}

/** Page opened from the e-mailed link: choose the new password. */
@Component({
  selector: 'rm-reset-password-page',
  imports: [ReactiveFormsModule, RouterLink, TranslocoPipe, FormError, ...MATERIAL],
  template: `
    <mat-card class="auth-card">
      <mat-card-header>
        <mat-card-title
          ><h1>{{ 'password.resetTitle' | transloco }}</h1></mat-card-title
        >
      </mat-card-header>
      <mat-card-content>
        @if (!token()) {
          <div class="notice notice-error" role="alert">
            {{ 'verify.missingToken' | transloco }}
          </div>
          <a routerLink="/esqueci-senha">{{ 'password.askAgain' | transloco }}</a>
        } @else {
          <form [formGroup]="form" (ngSubmit)="submit()" class="stack">
            <mat-form-field>
              <mat-label>{{ 'password.new' | transloco }}</mat-label>
              <input
                matInput
                type="password"
                formControlName="password"
                autocomplete="new-password"
              />
              <mat-hint>{{ 'password.rule' | transloco }}</mat-hint>
            </mat-form-field>
            <rm-form-error [error]="error()" />
            <button mat-flat-button type="submit" [disabled]="busy()">
              {{ 'password.save' | transloco }}
            </button>
          </form>
        }
      </mat-card-content>
    </mat-card>
  `,
})
export class ResetPasswordPage {
  private readonly api = inject(Api);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly token = input<string>();
  protected readonly form = inject(NonNullableFormBuilder).group({
    password: ['', Validators.required],
  });
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  async submit(): Promise<void> {
    const token = this.token();
    if (!token || this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.invoke(resetPassword, {
        body: { token, password: this.form.getRawValue().password },
      });
      // Every session was revoked on the server; drop this tab's one too.
      await this.auth.logout();
      await this.router.navigate(['/entrar'], { queryParams: { senha: '1' } });
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}

/** Profile card: change the password with the current one. */
@Component({
  selector: 'rm-change-password',
  imports: [ReactiveFormsModule, TranslocoPipe, FormError, ...MATERIAL],
  template: `
    <mat-card class="block">
      <mat-card-content>
        <h2>{{ 'password.changeTitle' | transloco }}</h2>
        <p class="muted">{{ 'password.changeHelp' | transloco }}</p>
        @if (saved()) {
          <p class="notice notice-ok" role="status">{{ 'password.changed' | transloco }}</p>
        }
        <form [formGroup]="form" (ngSubmit)="submit()" class="stack">
          <mat-form-field>
            <mat-label>{{ 'password.current' | transloco }}</mat-label>
            <input
              matInput
              type="password"
              formControlName="current_password"
              autocomplete="current-password"
            />
          </mat-form-field>
          <mat-form-field>
            <mat-label>{{ 'password.new' | transloco }}</mat-label>
            <input
              matInput
              type="password"
              formControlName="new_password"
              autocomplete="new-password"
            />
            <mat-hint>{{ 'password.rule' | transloco }}</mat-hint>
          </mat-form-field>
          <rm-form-error [error]="error()" />
          <div class="actions">
            <button mat-flat-button type="submit" [disabled]="busy()">
              {{ 'password.save' | transloco }}
            </button>
          </div>
        </form>
      </mat-card-content>
    </mat-card>
  `,
})
export class ChangePassword {
  private readonly api = inject(Api);
  protected readonly form = inject(NonNullableFormBuilder).group({
    current_password: ['', Validators.required],
    new_password: ['', Validators.required],
  });
  protected readonly busy = signal(false);
  protected readonly saved = signal(false);
  protected readonly error = signal<unknown>(null);

  async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.saved.set(false);
    try {
      await this.api.invoke(changePassword, { body: this.form.getRawValue() });
      this.form.reset();
      this.saved.set(true);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
