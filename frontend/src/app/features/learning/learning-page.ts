import { Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { createDemoProject } from '../../core/api/fn/learning/create-demo-project';
import { FormError } from '../../shared/form-error';

/** Glossary keys, in the order of the review (docs/dominio.md, section 5). */
const TERMS = [
  'systematicReview',
  'metaAnalysis',
  'pico',
  'protocol',
  'amendment',
  'screening',
  'fullText',
  'studyVsReport',
  'extraction',
  'sdSe',
  'riskOfBias',
  'domain',
  'signalling',
  'confounding',
  'adjusted',
  'effectMeasure',
  'smd',
  'ci',
  'fixed',
  'random',
  'heterogeneity',
  'i2',
  'tau2',
  'predictionInterval',
  'forest',
  'funnel',
  'sensitivity',
  'subgroup',
  'metaRegression',
  'unitOfAnalysis',
  'kappa',
  'grade',
  'prisma',
] as const;

const SOURCES: { key: string; url: string }[] = [
  { key: 'cochrane', url: 'https://training.cochrane.org/handbook' },
  { key: 'prisma', url: 'https://www.prisma-statement.org/' },
  { key: 'rob', url: 'https://www.riskofbias.info/' },
  { key: 'grade', url: 'https://gdt.gradepro.org/app/handbook/handbook.html' },
  { key: 'metafor', url: 'https://www.metafor-project.org/' },
];

/** Learning mode (7.11): the path of a review, a searchable glossary and a demo project. */
@Component({
  selector: 'rm-learning-page',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    FormError,
  ],
  template: `
    <h1>{{ 'learning.title' | transloco }}</h1>
    <p class="muted">{{ 'learning.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />

    <mat-card class="block">
      <mat-card-content>
        <h2>{{ 'learning.demoTitle' | transloco }}</h2>
        <p>{{ 'learning.demoText' | transloco }}</p>
        <button mat-flat-button type="button" [disabled]="busy()" (click)="demo()">
          {{ 'learning.demoButton' | transloco }}
        </button>
      </mat-card-content>
    </mat-card>

    <mat-card class="block">
      <mat-card-content>
        <h2>{{ 'learning.stepsTitle' | transloco }}</h2>
        <ol>
          @for (n of steps; track n) {
            <li>{{ 'learning.steps.' + n | transloco }}</li>
          }
        </ol>
      </mat-card-content>
    </mat-card>

    <mat-card class="block">
      <mat-card-content>
        <h2 id="glossary">{{ 'learning.glossaryTitle' | transloco }}</h2>
        <mat-form-field subscriptSizing="dynamic">
          <mat-label>{{ 'learning.search' | transloco }}</mat-label>
          <input matInput [ngModel]="query()" (ngModelChange)="query.set($event)" />
        </mat-form-field>
        <dl class="glossary">
          @for (key of visible(); track key) {
            <dt>{{ 'learning.terms.' + key + '.term' | transloco }}</dt>
            <dd>{{ 'learning.terms.' + key + '.text' | transloco }}</dd>
          } @empty {
            <p class="empty">{{ 'learning.noMatch' | transloco }}</p>
          }
        </dl>
      </mat-card-content>
    </mat-card>

    <mat-card class="block">
      <mat-card-content>
        <h2>{{ 'learning.sourcesTitle' | transloco }}</h2>
        <ul>
          @for (s of sources; track s.key) {
            <li>
              <a [href]="s.url" target="_blank" rel="noopener">{{
                'learning.sources.' + s.key | transloco
              }}</a>
            </li>
          }
        </ul>
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .glossary dt {
      font-weight: 600;
      margin-top: 0.75rem;
    }
    .glossary dd {
      margin: 0.25rem 0 0;
    }
  `,
})
export class LearningPage {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, {
    initialValue: this.transloco.getActiveLang(),
  });

  protected readonly steps = [1, 2, 3, 4, 5, 6, 7];
  protected readonly sources = SOURCES;
  protected readonly query = signal('');
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);

  /** Terms whose name or explanation contains the search (accents and case ignored). */
  protected readonly visible = computed(() => {
    this.lang();
    const wanted = plain(this.query());
    if (!wanted) return [...TERMS];
    return TERMS.filter((key) =>
      plain(
        this.transloco.translate(`learning.terms.${key}.term`) +
          ' ' +
          this.transloco.translate(`learning.terms.${key}.text`),
      ).includes(wanted),
    );
  });

  async demo(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const language = this.lang() === 'en' ? 'en' : 'pt-BR';
      const out = await this.api.invoke(createDemoProject, { body: { language } });
      await this.router.navigate(['/projetos', out.project_id]);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}

function plain(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}
