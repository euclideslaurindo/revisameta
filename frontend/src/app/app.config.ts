import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  isDevMode,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { TranslocoService, provideTransloco } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { routes } from './app.routes';
import { provideApiConfiguration } from './core/api/api-configuration';
import { authInterceptor } from './core/auth/auth-interceptor';
import { AuthService } from './core/auth/auth';
import { LANGUAGES, LanguageService } from './core/i18n/language';
import { TranslocoHttpLoader } from './core/i18n/transloco-loader';
import { PublicConfigService } from './core/public-config';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideApiConfiguration(''),
    provideTransloco({
      config: {
        availableLangs: [...LANGUAGES],
        defaultLang: 'pt-BR',
        fallbackLang: 'pt-BR',
        reRenderOnLangChange: true,
        prodMode: !isDevMode(),
      },
      loader: TranslocoHttpLoader,
    }),
    provideAppInitializer(async () => {
      const language = inject(LanguageService);
      const transloco = inject(TranslocoService);
      language.init();
      await Promise.all([
        firstValueFrom(transloco.load(language.current())),
        inject(PublicConfigService).load(),
        inject(AuthService).restoreSession(),
      ]);
    }),
  ],
};
