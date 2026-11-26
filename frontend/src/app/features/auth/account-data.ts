import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { deleteMyAccount } from '../../core/api/fn/auth/delete-my-account';
import { deletionCheck } from '../../core/api/fn/auth/deletion-check';
import { exportMyData } from '../../core/api/fn/auth/export-my-data';
import { DeletionCheckOut } from '../../core/api/models/deletion-check-out';
import { AuthService } from '../../core/auth/auth';
import { FormError } from '../../shared/form-error';

/** Profile card (LGPD): download my data and delete my account. */
@Component({
  selector: 'rm-account-data',
  imports: [
    FormsModule,
    RouterLink,
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
        <h2>{{ 'account.title' | transloco }}</h2>
        <p class="muted">{{ 'account.exportHelp' | transloco }}</p>
        <div class="actions">
          <button mat-stroked-button type="button" [disabled]="busy()" (click)="download()">
            {{ 'account.export' | transloco }}
          </button>
        </div>

        <h3>{{ 'account.deleteTitle' | transloco }}</h3>
        <p class="muted">{{ 'account.deleteHelp' | transloco }}</p>
        <rm-form-error [error]="error()" />
        @if (!check()) {
          <button mat-stroked-button type="button" [disabled]="busy()" (click)="start()">
            {{ 'account.deleteStart' | transloco }}
          </button>
        } @else {
          @let c = check()!;
          @if (c.blocking.length) {
            <div class="notice notice-warn" role="alert">
              <p>{{ 'account.blocking' | transloco }}</p>
              <ul>
                @for (b of c.blocking; track b.id) {
                  <li>
                    <a [routerLink]="['/projetos', b.id, 'configuracoes']">{{ b.title }}</a>
                    — {{ 'account.reason.' + b.reason | transloco }}
                  </li>
                }
              </ul>
            </div>
          } @else {
            <div class="notice notice-error" role="alert">
              <p>{{ 'account.warning' | transloco }}</p>
              @if (c.projects_deleted.length) {
                <p>{{ 'account.soloProjects' | transloco }}</p>
                <ul>
                  @for (t of c.projects_deleted; track t) {
                    <li>{{ t }}</li>
                  }
                </ul>
              }
              @if (c.memberships_left) {
                <p>
                  {{ 'account.leaves' | transloco: { count: c.memberships_left } }}
                </p>
              }
            </div>
            <mat-form-field>
              <mat-label>{{ 'password.current' | transloco }}</mat-label>
              <input
                matInput
                type="password"
                autocomplete="current-password"
                [ngModel]="password()"
                (ngModelChange)="password.set($event)"
              />
            </mat-form-field>
            @if (auth.user()?.two_factor) {
              <mat-form-field>
                <mat-label>{{ 'login.otp' | transloco }}</mat-label>
                <input
                  matInput
                  autocomplete="one-time-code"
                  maxlength="20"
                  [ngModel]="otp()"
                  (ngModelChange)="otp.set($event)"
                />
              </mat-form-field>
            }
            <div class="actions">
              <button
                mat-flat-button
                color="warn"
                type="button"
                [disabled]="busy() || !password()"
                (click)="remove()"
              >
                {{ 'account.deleteConfirm' | transloco }}
              </button>
              <button mat-button type="button" (click)="check.set(null)">
                {{ 'common.cancel' | transloco }}
              </button>
            </div>
          }
        }
      </mat-card-content>
    </mat-card>
  `,
})
export class AccountData {
  private readonly api = inject(Api);
  protected readonly auth = inject(AuthService);

  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly check = signal<DeletionCheckOut | null>(null);
  protected readonly password = signal('');
  protected readonly otp = signal('');

  async download(): Promise<void> {
    await this.run(async () => {
      const data = await this.api.invoke(exportMyData, {});
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `revisameta-meus-dados-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  async start(): Promise<void> {
    await this.run(async () => this.check.set(await this.api.invoke(deletionCheck, {})));
  }

  async remove(): Promise<void> {
    await this.run(async () => {
      await this.api.invoke(deleteMyAccount, {
        body: { password: this.password(), otp_code: this.otp().trim() || null },
      });
      await this.auth.logout();
    });
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
