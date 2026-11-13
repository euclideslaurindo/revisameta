import { HttpContext, HttpContextToken } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { Api } from '../api/api';
import { login } from '../api/fn/auth/login';
import { logout } from '../api/fn/auth/logout';
import { refresh } from '../api/fn/auth/refresh';
import { register } from '../api/fn/auth/register';
import { updateMe } from '../api/fn/auth/update-me';
import { RegisterIn } from '../api/models/register-in';
import { TokenOut } from '../api/models/token-out';
import { UserOut } from '../api/models/user-out';
import { Language } from '../i18n/language';

/** Marks requests that must not trigger the automatic refresh-and-retry. */
export const SKIP_REFRESH = new HttpContextToken<boolean>(() => false);

/**
 * Session state (ADR-006): the access token lives only in memory; the refresh token
 * is an httpOnly cookie the browser sends to /api/v1/auth automatically.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(Api);
  private readonly router = inject(Router);

  private readonly token = signal<string | null>(null);
  readonly user = signal<UserOut | null>(null);
  readonly isLoggedIn = computed(() => this.user() !== null);

  private refreshing: Promise<boolean> | null = null;

  accessToken(): string | null {
    return this.token();
  }

  private accept(result: TokenOut): void {
    this.token.set(result.access_token);
    this.user.set(result.user);
  }

  private clear(): void {
    this.token.set(null);
    this.user.set(null);
  }

  private noRefresh(): HttpContext {
    return new HttpContext().set(SKIP_REFRESH, true);
  }

  async login(email: string, password: string, captchaToken?: string | null): Promise<UserOut> {
    const result = await this.api.invoke(
      login,
      { body: { email, password, captcha_token: captchaToken ?? null } },
      this.noRefresh(),
    );
    this.accept(result);
    return result.user;
  }

  register(body: RegisterIn): Promise<UserOut> {
    return this.api.invoke(register, { body }, this.noRefresh());
  }

  /** Silent refresh. Concurrent callers share the same request. */
  refresh(): Promise<boolean> {
    this.refreshing ??= this.api
      .invoke(refresh, undefined, this.noRefresh())
      .then((result) => {
        this.accept(result);
        return true;
      })
      .catch(() => {
        this.clear();
        return false;
      })
      .finally(() => {
        this.refreshing = null;
      });
    return this.refreshing;
  }

  /** Called once at startup: restores the session from the refresh cookie, if any. */
  async restoreSession(): Promise<void> {
    await this.refresh();
  }

  async logout(): Promise<void> {
    try {
      await this.api.invoke(logout, undefined, this.noRefresh());
    } finally {
      this.clear();
      await this.router.navigateByUrl('/entrar');
    }
  }

  async expire(): Promise<void> {
    this.clear();
    await this.router.navigate(['/entrar'], { queryParams: { sessao: 'expirada' } });
  }

  async saveLanguage(language: Language): Promise<void> {
    if (!this.isLoggedIn()) return;
    const user = await this.api.invoke(updateMe, { body: { ui_language: language } });
    this.user.set(user);
  }
}
