import { Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { resendVerification } from '../../core/api/fn/auth/resend-verification';
import { AuthService } from '../../core/auth/auth';
import { LanguageService } from '../../core/i18n/language';
import { PublicConfigService } from '../../core/public-config';
import { FormError } from '../../shared/form-error';
import { Turnstile } from '../../shared/turnstile';

@Component({
  selector: 'rm-register-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
    Turnstile,
  ],
  template: `
    @if (sentTo(); as email) {
      <mat-card class="auth-card">
        <mat-card-header>
          <mat-card-title
            ><h1>{{ 'register.doneTitle' | transloco }}</h1></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <p>{{ 'register.doneText' | transloco: { email } }}</p>
          @if (resent()) {
            <div class="notice" role="status">{{ 'register.resent' | transloco }}</div>
          }
          <button mat-stroked-button type="button" (click)="resend(email)">
            {{ 'register.resend' | transloco }}
          </button>
        </mat-card-content>
      </mat-card>
    } @else {
      <mat-card class="auth-card">
        <mat-card-header>
          <mat-card-title
            ><h1>{{ 'register.title' | transloco }}</h1></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <form [formGroup]="form" (ngSubmit)="submit()" class="stack">
            <mat-form-field>
              <mat-label>{{ 'common.name' | transloco }}</mat-label>
              <input matInput formControlName="name" autocomplete="name" />
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'common.email' | transloco }}</mat-label>
              <input matInput type="email" formControlName="email" autocomplete="email" />
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'common.password' | transloco }}</mat-label>
              <input
                matInput
                type="password"
                formControlName="password"
                autocomplete="new-password"
              />
              <mat-hint>{{ 'register.passwordHint' | transloco }}</mat-hint>
            </mat-form-field>

            <mat-checkbox formControlName="acceptTerms"
              >{{ 'legal.registerAccept' | transloco }}
              <a routerLink="/termos" target="_blank">{{ 'legal.termsLink' | transloco }}</a>
              {{ 'legal.and' | transloco }}
              <a routerLink="/privacidade" target="_blank">{{
                'legal.privacyLink' | transloco
              }}</a></mat-checkbox
            >

            @if (config.captchaSiteKey(); as key) {
              <rm-turnstile
                [siteKey]="key"
                [language]="language.current()"
                (token)="captcha.set($event)"
              />
            }

            <rm-form-error [error]="error()" />
            <button mat-flat-button type="submit" [disabled]="busy()">
              {{ 'register.submit' | transloco }}
            </button>
          </form>
          <p class="muted">
            {{ 'register.haveAccount' | transloco }}
            <a routerLink="/entrar">{{ 'login.submit' | transloco }}</a>
          </p>
        </mat-card-content>
      </mat-card>
    }
  `,
})
export class RegisterPage {
  private readonly auth = inject(AuthService);
  private readonly api = inject(Api);
  protected readonly config = inject(PublicConfigService);
  protected readonly language = inject(LanguageService);

  protected readonly form = inject(NonNullableFormBuilder).group({
    name: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(10)]],
    acceptTerms: [false, Validators.requiredTrue],
  });
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly captcha = signal<string | null>(null);
  protected readonly sentTo = signal<string | null>(null);
  protected readonly resent = signal(false);

  async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    const value = this.form.getRawValue();
    try {
      await this.auth.register({
        name: value.name,
        email: value.email,
        password: value.password,
        accept_terms: value.acceptTerms,
        language: this.language.current(),
        captcha_token: this.captcha(),
      });
      this.sentTo.set(value.email);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }

  async resend(email: string): Promise<void> {
    await this.api.invoke(resendVerification, { body: { email } });
    this.resent.set(true);
  }
}
