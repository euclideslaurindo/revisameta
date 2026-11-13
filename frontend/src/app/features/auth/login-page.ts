import { Component, inject, input, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { AuthService } from '../../core/auth/auth';
import { asProblem } from '../../core/errors/problem';
import { LanguageService } from '../../core/i18n/language';
import { PublicConfigService } from '../../core/public-config';
import { FormError } from '../../shared/form-error';
import { Turnstile } from '../../shared/turnstile';

@Component({
  selector: 'rm-login-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
    Turnstile,
  ],
  template: `
    <mat-card class="auth-card">
      <mat-card-header>
        <mat-card-title><h1>{{ 'login.title' | transloco }}</h1></mat-card-title>
      </mat-card-header>
      <mat-card-content>
        @if (sessao() === 'expirada') {
          <div class="notice notice-warn" role="status">{{ 'login.sessionExpired' | transloco }}</div>
        }
        @if (verificado()) {
          <div class="notice notice-ok" role="status">{{ 'login.verified' | transloco }}</div>
        }
        <form [formGroup]="form" (ngSubmit)="submit()" class="stack">
          <mat-form-field>
            <mat-label>{{ 'common.email' | transloco }}</mat-label>
            <input matInput type="email" formControlName="email" autocomplete="email" />
          </mat-form-field>
          <mat-form-field>
            <mat-label>{{ 'common.password' | transloco }}</mat-label>
            <input matInput type="password" formControlName="password" autocomplete="current-password" />
          </mat-form-field>

          @if (needsCaptcha() && config.captchaSiteKey(); as key) {
            <rm-turnstile [siteKey]="key" [language]="language.current()" (token)="captcha.set($event)" />
          }

          <rm-form-error [error]="error()" />
          <button mat-flat-button type="submit" [disabled]="form.invalid || busy()">
            {{ 'login.submit' | transloco }}
          </button>
        </form>
        <p class="muted">
          {{ 'login.noAccount' | transloco }}
          <a routerLink="/cadastro">{{ 'login.createAccount' | transloco }}</a>
        </p>
      </mat-card-content>
    </mat-card>
  `,
})
export class LoginPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  protected readonly config = inject(PublicConfigService);
  protected readonly language = inject(LanguageService);

  /** Query params bound by the router. */
  readonly voltar = input<string>();
  readonly sessao = input<string>();
  readonly verificado = input<string>();

  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly needsCaptcha = signal(false);
  protected readonly captcha = signal<string | null>(null);

  async submit(): Promise<void> {
    if (this.form.invalid) return;
    this.busy.set(true);
    this.error.set(null);
    const { email, password } = this.form.getRawValue();
    try {
      await this.auth.login(email, password, this.captcha());
      const target = this.voltar();
      await this.router.navigateByUrl(target?.startsWith('/') ? target : '/projetos');
    } catch (error) {
      this.error.set(error);
      if (asProblem(error)?.code === 'auth.captcha_failed') this.needsCaptcha.set(true);
    } finally {
      this.busy.set(false);
    }
  }
}
