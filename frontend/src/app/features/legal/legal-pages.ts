import { Component, computed, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { Router, RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { acceptTerms } from '../../core/api/fn/auth/accept-terms';
import { AuthService } from '../../core/auth/auth';
import { PublicConfigService } from '../../core/public-config';
import { FormError } from '../../shared/form-error';

type Kind = 'terms' | 'privacy';
const SECTIONS: Record<Kind, number> = { terms: 11, privacy: 10 };

/** Terms of use or privacy policy (10.2). Public: readable before signing up. */
@Component({
  selector: 'rm-legal-page',
  imports: [TranslocoPipe, RouterLink, MatCardModule],
  template: `
    <mat-card class="block legal">
      <mat-card-content>
        <h1>{{ 'legal.' + kind() + '.title' | transloco }}</h1>
        <p class="muted">
          {{ 'legal.updated' | transloco: { version: version() } }} ·
          {{ 'legal.draft' | transloco }}
        </p>
        @for (n of sections(); track n) {
          <h2>{{ n }}. {{ 'legal.' + kind() + '.sections.' + n + '.0' | transloco }}</h2>
          <p class="pre">
            {{ 'legal.' + kind() + '.sections.' + n + '.1' | transloco: { contact: contact() } }}
          </p>
        }
        <p>
          @if (kind() === 'terms') {
            <a routerLink="/privacidade">{{ 'legal.privacyLink' | transloco }}</a>
          } @else {
            <a routerLink="/termos">{{ 'legal.termsLink' | transloco }}</a>
          }
        </p>
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .legal {
      max-width: 52rem;
    }
    .pre {
      white-space: pre-line;
    }
  `,
})
export class LegalPage {
  private readonly config = inject(PublicConfigService);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, {
    initialValue: this.transloco.getActiveLang(),
  });

  /** Set by the route data. */
  readonly kind = input<Kind>('terms');
  protected readonly sections = computed(() =>
    Array.from({ length: SECTIONS[this.kind()] }, (_, i) => i + 1),
  );
  protected readonly version = computed(() => this.config.config()?.terms_version ?? '');
  protected readonly contact = computed(() => {
    this.lang();
    return (
      this.config.config()?.legal_contact_email || this.transloco.translate('legal.contactMissing')
    );
  });
}

/** Shown to signed-in users whose accepted version is older than the current one. */
@Component({
  selector: 'rm-accept-terms-page',
  imports: [TranslocoPipe, RouterLink, MatButtonModule, MatCardModule, FormError],
  template: `
    <mat-card class="auth-card">
      <mat-card-content>
        <h1>{{ 'legal.acceptTitle' | transloco }}</h1>
        <p>{{ 'legal.acceptText' | transloco }}</p>
        <ul>
          <li>
            <a routerLink="/termos" target="_blank">{{ 'legal.termsLink' | transloco }}</a>
          </li>
          <li>
            <a routerLink="/privacidade" target="_blank">{{ 'legal.privacyLink' | transloco }}</a>
          </li>
        </ul>
        <rm-form-error [error]="error()" />
        <div class="actions">
          <button mat-flat-button type="button" [disabled]="busy()" (click)="accept()">
            {{ 'legal.acceptButton' | transloco }}
          </button>
          <button mat-button type="button" (click)="auth.logout()">
            {{ 'app.logout' | transloco }}
          </button>
        </div>
      </mat-card-content>
    </mat-card>
  `,
})
export class AcceptTermsPage {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  private readonly config = inject(PublicConfigService);
  protected readonly auth = inject(AuthService);

  readonly voltar = input<string>();
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  async accept(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.config.load();
      const version = this.config.config()?.terms_version ?? '';
      this.auth.user.set(await this.api.invoke(acceptTerms, { body: { version } }));
      const target = this.voltar();
      await this.router.navigateByUrl(target?.startsWith('/') ? target : '/projetos');
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
