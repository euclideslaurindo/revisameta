import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { AuthService } from './core/auth/auth';
import { ThemeChoice, ThemeService } from './core/theme';
import { LANGUAGES, Language, LanguageService } from './core/i18n/language';
import { NotificationsMenu } from './shared/notifications-menu';

@Component({
  selector: 'rm-root',
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    TranslocoPipe,
    MatButtonModule,
    MatMenuModule,
    NotificationsMenu,
  ],
  template: `
    <a class="skip-link" href="#main">{{ 'app.skipToContent' | transloco }}</a>
    <div class="beta-banner" role="note">{{ 'app.beta' | transloco }}</div>
    <header class="topbar">
      <a routerLink="/" class="brand">
        <img src="logo.svg" alt="" />
        <span>{{ 'app.name' | transloco }}</span>
      </a>
      @if (auth.user(); as user) {
        <nav [attr.aria-label]="'app.mainNav' | transloco">
          <a routerLink="/projetos" routerLinkActive="active">{{ 'app.projects' | transloco }}</a>
          <a routerLink="/aprendizado" routerLinkActive="active">{{
            'app.learning' | transloco
          }}</a>
          @if (user.is_system_admin) {
            <a routerLink="/admin" routerLinkActive="active">{{ 'app.admin' | transloco }}</a>
          }
        </nav>
      }
      <span class="spacer"></span>
      <label class="sr-only" for="ui-language">{{ 'app.language' | transloco }}</label>
      <select
        id="ui-language"
        class="lang-select"
        [value]="language.current()"
        (change)="changeLanguage($any($event.target).value)"
      >
        @for (lang of languages; track lang) {
          <option [value]="lang" [selected]="lang === language.current()">
            {{ 'languages.' + lang | transloco }}
          </option>
        }
      </select>
      @if (auth.user(); as user) {
        <rm-notifications-menu class="on-dark" />
        <button
          type="button"
          class="top-button"
          [matMenuTriggerFor]="userMenu"
          [attr.aria-label]="user.name"
        >
          <span class="avatar" aria-hidden="true">{{ initials(user.name) }}</span>
          <span class="user-name">{{ user.name }}</span>
        </button>
        <mat-menu #userMenu="matMenu">
          <a mat-menu-item routerLink="/perfil">{{ 'app.profile' | transloco }}</a>
          @for (t of themes; track t) {
            <button
              mat-menu-item
              type="button"
              role="menuitemradio"
              [attr.aria-checked]="theme.choice() === t"
              (click)="theme.set(t)"
            >
              {{ theme.choice() === t ? '✓ ' : '' }}{{ 'app.theme.' + t | transloco }}
            </button>
          }
          <!-- On phones the language select is hidden from the bar and lives here. -->
          @for (lang of languages; track lang) {
            @if (lang !== language.current()) {
              <button
                mat-menu-item
                type="button"
                class="menu-language"
                (click)="changeLanguage(lang)"
              >
                {{ 'languages.' + lang | transloco }}
              </button>
            }
          }
          <button mat-menu-item type="button" (click)="auth.logout()">
            {{ 'app.logout' | transloco }}
          </button>
        </mat-menu>
      }
    </header>
    <main id="main" tabindex="-1">
      <router-outlet />
    </main>
    <footer class="footer">
      <span>{{ 'app.footer' | transloco }}</span>
      <a routerLink="/termos">{{ 'legal.termsLink' | transloco }}</a>
      <a routerLink="/privacidade">{{ 'legal.privacyLink' | transloco }}</a>
    </footer>
  `,
})
export class App {
  protected readonly auth = inject(AuthService);
  protected readonly language = inject(LanguageService);
  protected readonly languages = LANGUAGES;
  protected readonly theme = inject(ThemeService);
  protected readonly themes: ThemeChoice[] = ['auto', 'light', 'dark'];

  protected initials(name: string): string {
    const parts = name.trim().split(/\s+/);
    return (
      (parts[0]?.[0] ?? '') + (parts.length > 1 ? (parts.at(-1)?.[0] ?? '') : '')
    ).toUpperCase();
  }

  protected changeLanguage(language: Language): void {
    this.language.set(language);
    void this.auth.saveLanguage(language);
  }
}
