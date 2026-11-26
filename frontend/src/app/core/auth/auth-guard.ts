import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth';

/** Signed in, whatever the terms version (used by the page that asks to accept them). */
export const loggedInGuard: CanActivateFn = (_route, state) => {
  if (inject(AuthService).isLoggedIn()) {
    return true;
  }
  return inject(Router).createUrlTree(['/entrar'], { queryParams: { voltar: state.url } });
};

/** Signed in and with the current terms accepted (10.2). */
export const authGuard: CanActivateFn = (route, state) => {
  const user = inject(AuthService).user();
  if (user?.terms_outdated) {
    return inject(Router).createUrlTree(['/aceitar-termos'], {
      queryParams: { voltar: state.url },
    });
  }
  return loggedInGuard(route, state);
};

export const guestGuard: CanActivateFn = () =>
  inject(AuthService).isLoggedIn() ? inject(Router).createUrlTree(['/projetos']) : true;

/** System administrators only (screen 21); the backend checks again on every call. */
export const systemAdminGuard: CanActivateFn = (route, state) => {
  const allowed = authGuard(route, state);
  if (allowed !== true) return allowed;
  return inject(AuthService).user()?.is_system_admin
    ? true
    : inject(Router).createUrlTree(['/projetos']);
};
