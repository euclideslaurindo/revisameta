import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth/auth-guard';

// Paths match the links the backend puts in e-mails (/verificar-email, /convite).
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'projetos' },
  {
    path: 'entrar',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login-page').then((m) => m.LoginPage),
  },
  {
    path: 'cadastro',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/register-page').then((m) => m.RegisterPage),
  },
  {
    path: 'verificar-email',
    loadComponent: () =>
      import('./features/auth/verify-email-page').then((m) => m.VerifyEmailPage),
  },
  {
    path: 'convite',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/invitation/invitation-page').then((m) => m.InvitationPage),
  },
  {
    path: 'projetos',
    canActivate: [authGuard],
    loadComponent: () => import('./features/projects/projects-page').then((m) => m.ProjectsPage),
  },
  {
    path: 'projetos/:projectId',
    canActivate: [authGuard],
    loadComponent: () => import('./features/project/project-shell').then((m) => m.ProjectShell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'protocolo' },
      {
        path: 'protocolo',
        loadComponent: () =>
          import('./features/protocol/protocol-page').then((m) => m.ProtocolPage),
      },
    ],
  },
  {
    path: '**',
    loadComponent: () => import('./features/not-found-page').then((m) => m.NotFoundPage),
  },
];
