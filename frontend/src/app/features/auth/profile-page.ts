import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { twoFactorDisable } from '../../core/api/fn/auth/two-factor-disable';
import { twoFactorEnable } from '../../core/api/fn/auth/two-factor-enable';
import { twoFactorSetup } from '../../core/api/fn/auth/two-factor-setup';
import { AuthService } from '../../core/auth/auth';
import { withJsonBody } from '../../core/errors/problem';
import { FormError } from '../../shared/form-error';
import { AccountData } from './account-data';
import { ChangePassword } from './password-pages';

/** My profile: optional two-step verification with an authenticator app (TOTP). */
@Component({
  selector: 'rm-profile-page',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
    ChangePassword,
    AccountData,
  ],
  template: `
    <h1>{{ 'profile.title' | transloco }}</h1>
    <rm-change-password />
    <mat-card class="block">
      <mat-card-content>
        <h2>{{ 'profile.twoFactor' | transloco }}</h2>
        <p class="muted">{{ 'profile.twoFactorHelp' | transloco }}</p>
        <rm-form-error [error]="error()" />
        <p>
          <strong>{{ (on() ? 'profile.on' : 'profile.off') | transloco }}</strong>
        </p>
        @if (codes(); as list) {
          <p class="warning" role="alert">{{ 'profile.codes' | transloco }}</p>
          <ul class="codes">
            @for (c of list; track c) {
              <li>
                <code>{{ c }}</code>
              </li>
            }
          </ul>
        }
        @if (!on()) {
          @if (setup(); as s) {
            <p>
              {{ 'profile.secret' | transloco }} <code>{{ s.secret }}</code>
            </p>
            <p>
              <a [href]="uri(s.otpauth_uri)">{{ 'profile.openApp' | transloco }}</a>
            </p>
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'profile.code' | transloco }}</mat-label>
              <input
                matInput
                inputmode="numeric"
                autocomplete="one-time-code"
                maxlength="6"
                [(ngModel)]="code"
              />
            </mat-form-field>
            <button mat-flat-button type="button" [disabled]="busy()" (click)="enable()">
              {{ 'profile.confirm' | transloco }}
            </button>
          } @else {
            <button mat-flat-button type="button" [disabled]="busy()" (click)="start()">
              {{ 'profile.start' | transloco }}
            </button>
          }
        } @else {
          <p class="muted">{{ 'profile.disableHelp' | transloco }}</p>
          <div class="row">
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'profile.password' | transloco }}</mat-label>
              <input
                matInput
                type="password"
                autocomplete="current-password"
                [(ngModel)]="password"
              />
            </mat-form-field>
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ 'login.otp' | transloco }}</mat-label>
              <input matInput autocomplete="one-time-code" maxlength="20" [(ngModel)]="code" />
            </mat-form-field>
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="disable()">
              {{ 'profile.disable' | transloco }}
            </button>
          </div>
        }
      </mat-card-content>
    </mat-card>
    <rm-account-data />
  `,
})
export class ProfilePage {
  private readonly api = inject(Api);
  private readonly auth = inject(AuthService);
  private readonly sanitizer = inject(DomSanitizer);

  protected readonly on = signal(this.auth.user()?.two_factor ?? false);
  protected readonly setup = signal<{ secret: string; otpauth_uri: string } | null>(null);
  protected readonly codes = signal<string[] | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected code = '';
  protected password = '';

  /** otpauth:// links are not http(s); allow this one explicitly so phones can open it. */
  protected uri(value: string): SafeUrl {
    return value.startsWith('otpauth://') ? this.sanitizer.bypassSecurityTrustUrl(value) : '';
  }

  async start(): Promise<void> {
    await this.guard(async () => this.setup.set(await this.api.invoke(twoFactorSetup, {})));
  }

  async enable(): Promise<void> {
    await this.guard(async () => {
      const out = await this.api.invoke(twoFactorEnable, { body: { code: this.code.trim() } });
      this.codes.set(out.recovery_codes);
      this.on.set(true);
      this.setup.set(null);
      this.code = '';
    });
  }

  async disable(): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(twoFactorDisable, {
        body: { password: this.password, code: this.code.trim() },
      });
      this.on.set(false);
      this.codes.set(null);
      this.code = '';
      this.password = '';
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
