import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink, RouterOutlet } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { AuthService } from './core/auth/auth';
import { LANGUAGES, Language, LanguageService } from './core/i18n/language';
import { NotificationsMenu } from './shared/notifications-menu';

@Component({
  selector: 'rm-root',
  imports: [
    RouterLink,
    RouterOutlet,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    NotificationsMenu,
  ],
  template: `
    <a class="skip-link" href="#main">{{ 'app.skipToContent' | transloco }}</a>
    <div class="beta-banner" role="note">{{ 'app.beta' | transloco }}</div>
    <header class="topbar">
      <a routerLink="/" class="brand">{{ 'app.name' | transloco }}</a>
      <span class="spacer"></span>
      <mat-form-field class="language" subscriptSizing="dynamic">
        <mat-label>{{ 'app.language' | transloco }}</mat-label>
        <mat-select [value]="language.current()" (valueChange)="changeLanguage($event)">
          @for (lang of languages; track lang) {
            <mat-option [value]="lang">{{ 'languages.' + lang | transloco }}</mat-option>
          }
        </mat-select>
      </mat-form-field>
      @if (auth.user(); as user) {
        <a routerLink="/aprendizado">{{ 'app.learning' | transloco }}</a>
        <rm-notifications-menu />
        <a class="user" routerLink="/perfil">{{ user.name }}</a>
        <button mat-button type="button" (click)="auth.logout()">
          {{ 'app.logout' | transloco }}
        </button>
      }
    </header>
    <main id="main" tabindex="-1">
      <router-outlet />
    </main>
    <footer class="footer">
      <a routerLink="/termos">{{ 'legal.termsLink' | transloco }}</a>
      <a routerLink="/privacidade">{{ 'legal.privacyLink' | transloco }}</a>
    </footer>
  `,
})
export class App {
  protected readonly auth = inject(AuthService);
  protected readonly language = inject(LanguageService);
  protected readonly languages = LANGUAGES;

  protected changeLanguage(language: Language): void {
    this.language.set(language);
    void this.auth.saveLanguage(language);
  }
}
