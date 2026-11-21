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
    loadComponent: () => import('./features/auth/verify-email-page').then((m) => m.VerifyEmailPage),
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
      {
        path: 'buscas/duplicatas',
        loadComponent: () =>
          import('./features/references/duplicates-page').then((m) => m.DuplicatesPage),
      },
      {
        path: 'buscas',
        loadComponent: () =>
          import('./features/references/searches-page').then((m) => m.SearchesPage),
      },
      {
        path: 'triagem',
        loadComponent: () =>
          import('./features/screening/screening-page').then((m) => m.ScreeningPage),
      },
      {
        path: 'estudos',
        loadComponent: () => import('./features/studies/studies-page').then((m) => m.StudiesPage),
      },
      {
        path: 'estudos/importar',
        loadComponent: () => import('./features/studies/import-page').then((m) => m.ImportPage),
      },
      {
        path: 'estudos/:studyId',
        loadComponent: () => import('./features/studies/study-page').then((m) => m.StudyPage),
      },
      {
        path: 'estudos/:studyId/consenso',
        loadComponent: () =>
          import('./features/extraction/consensus-page').then((m) => m.ConsensusPage),
      },
      {
        path: 'extracoes/:extractionId',
        loadComponent: () =>
          import('./features/extraction/extraction-page').then((m) => m.ExtractionPage),
      },
      {
        path: 'risco-de-vies/estudos/:studyId/consenso',
        loadComponent: () =>
          import('./features/risk-of-bias/rob-consensus-page').then((m) => m.RobConsensusPage),
      },
      {
        path: 'risco-de-vies/importar',
        loadComponent: () =>
          import('./features/risk-of-bias/rob-import-page').then((m) => m.RobImportPage),
      },
      {
        path: 'risco-de-vies/revisao',
        loadComponent: () =>
          import('./features/risk-of-bias/rob-review-page').then((m) => m.RobReviewPage),
      },
      {
        path: 'risco-de-vies/tabela',
        loadComponent: () =>
          import('./features/risk-of-bias/rob-table-page').then((m) => m.RobTablePage),
      },
      {
        path: 'risco-de-vies/avaliacoes/:assessmentId',
        loadComponent: () =>
          import('./features/risk-of-bias/rob-assessment-page').then((m) => m.RobAssessmentPage),
      },
      {
        path: 'risco-de-vies',
        loadComponent: () => import('./features/risk-of-bias/rob-page').then((m) => m.RobPage),
      },
      {
        path: 'meta-analise',
        loadComponent: () =>
          import('./features/meta-analysis/meta-analysis-page').then((m) => m.MetaAnalysisPage),
      },
      {
        path: 'conferencia',
        loadComponent: () => import('./features/extraction/review-page').then((m) => m.ReviewPage),
      },
      {
        path: 'exportar',
        loadComponent: () => import('./features/exports/export-page').then((m) => m.ExportPage),
      },
      {
        path: 'pendencias',
        loadComponent: () =>
          import('./features/extraction/pending-page').then((m) => m.PendingPage),
      },
      {
        path: 'pdfs/:pdfId',
        loadComponent: () => import('./features/pdfs/pdf-viewer-page').then((m) => m.PdfViewerPage),
      },
    ],
  },
  {
    path: '**',
    loadComponent: () => import('./features/not-found-page').then((m) => m.NotFoundPage),
  },
];
