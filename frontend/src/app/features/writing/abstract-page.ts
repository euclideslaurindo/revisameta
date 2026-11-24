import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { draftAbstract } from '../../core/api/fn/writing/draft-abstract';
import { getAbstract } from '../../core/api/fn/writing/get-abstract';
import { methodsResults } from '../../core/api/fn/writing/methods-results';
import { saveAbstract } from '../../core/api/fn/writing/save-abstract';
import { OutcomeOut } from '../../core/api/models/outcome-out';
import { withJsonBody } from '../../core/errors/problem';
import { fileNameFrom, saveFile } from '../../shared/download';
import { FormError } from '../../shared/form-error';
import { PrismaChecklist } from '../prisma/prisma-checklist';
import { ProjectContext } from '../project/project-context';
import { countWords } from './text-count';

/**
 * Abstract for the congress (docs/modulos.md 7.14): PRISMA for Abstracts checklist, a
 * structured draft filled with the system's numbers (no AI), word and character
 * counters against the congress limits, and the Methods/Results draft (DOCX).
 */
@Component({
  selector: 'rm-abstract-page',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    FormError,
    PrismaChecklist,
  ],
  template: `
    <mat-card class="block">
      <mat-card-content>
        <h2>{{ 'writing.title' | transloco }}</h2>
        <p class="muted">{{ 'writing.intro' | transloco }}</p>
        <rm-form-error [error]="error()" />
        <div class="row">
          <mat-form-field subscriptSizing="dynamic" class="wide">
            <mat-label>{{ 'writing.outcome' | transloco }}</mat-label>
            <mat-select [(ngModel)]="result">
              <mat-option [value]="null">{{ 'writing.noOutcome' | transloco }}</mat-option>
              @for (o of outcomes(); track o.id) {
                @for (t of o.timepoints; track t) {
                  <mat-option [value]="o.id + '|' + t">{{ o.name }} · {{ t }}</mat-option>
                }
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'writing.lang' | transloco }}</mat-label>
            <mat-select [(ngModel)]="lang">
              <mat-option value="pt-BR">Português</mat-option>
              <mat-option value="en">English</mat-option>
            </mat-select>
          </mat-form-field>
          <button mat-stroked-button type="button" [disabled]="busy()" (click)="draft()">
            {{ 'writing.draft' | transloco }}
          </button>
          <button mat-stroked-button type="button" [disabled]="busy()" (click)="docx()">
            {{ 'writing.docx' | transloco }}
          </button>
        </div>

        <div class="row">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'writing.wordLimit' | transloco }}</mat-label>
            <input matInput type="number" min="1" [(ngModel)]="wordLimit" />
          </mat-form-field>
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'writing.charLimit' | transloco }}</mat-label>
            <input matInput type="number" min="1" [(ngModel)]="charLimit" />
          </mat-form-field>
        </div>
        <mat-form-field subscriptSizing="dynamic" class="full">
          <mat-label>{{ 'writing.text' | transloco }}</mat-label>
          <textarea
            matInput
            rows="14"
            maxlength="20000"
            [ngModel]="text()"
            (ngModelChange)="text.set($event)"
          ></textarea>
        </mat-form-field>
        <p role="status" [class.warning]="over()">
          {{ 'writing.count' | transloco: { words: words(), chars: chars() } }}
          @if (wordLimit) {
            · {{ 'writing.ofWords' | transloco: { limit: wordLimit } }}
          }
          @if (charLimit) {
            · {{ 'writing.ofChars' | transloco: { limit: charLimit } }}
          }
          @if (over()) {
            — <strong>{{ 'writing.over' | transloco }}</strong>
          }
        </p>
        <button mat-flat-button type="button" [disabled]="busy()" (click)="save()">
          {{ 'writing.save' | transloco }}
        </button>
        @if (saved()) {
          <span class="muted" role="status">{{ 'writing.saved' | transloco }}</span>
        }
      </mat-card-content>
    </mat-card>
    <rm-prisma-checklist kind="abstracts" />
  `,
  styles: `
    .full {
      width: 100%;
    }
  `,
})
export class AbstractPage implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);

  protected readonly outcomes = signal<OutcomeOut[]>([]);
  protected readonly text = signal('');
  protected readonly busy = signal(false);
  protected readonly saved = signal(false);
  protected readonly error = signal<unknown>(null);
  protected result: string | null = null;
  protected lang: 'pt-BR' | 'en' = 'pt-BR';
  protected wordLimit: number | null = null;
  protected charLimit: number | null = null;
  private version: number | null = null;

  protected readonly words = computed(() => countWords(this.text()));
  protected readonly chars = computed(() => this.text().length);

  protected over(): boolean {
    return (
      (!!this.wordLimit && this.words() > this.wordLimit) ||
      (!!this.charLimit && this.chars() > this.charLimit)
    );
  }

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(async () => {
      const project_id = this.projectId();
      const [outcomes, abstract] = await Promise.all([
        this.api.invoke(listOutcomes, { project_id }),
        this.api.invoke(getAbstract, { project_id }),
      ]);
      this.outcomes.set(outcomes);
      this.text.set(abstract.text);
      this.wordLimit = abstract.word_limit ?? null;
      this.charLimit = abstract.char_limit ?? null;
      this.version = abstract.version ?? null;
    });
  }

  private body() {
    if (!this.result) return { lang: this.lang };
    const [outcome_id, timepoint] = this.result.split('|');
    return { lang: this.lang, analysis: { outcome_id, timepoint } };
  }

  async draft(): Promise<void> {
    await this.guard(async () => {
      const s = await this.api.invoke(draftAbstract, {
        project_id: this.projectId(),
        body: this.body(),
      });
      const t =
        this.lang === 'en'
          ? ['Objective', 'Methods', 'Results', 'Conclusion']
          : ['Objetivo', 'Métodos', 'Resultados', 'Conclusão'];
      this.text.set(
        [s.objective, s.methods, s.results, s.conclusion]
          .map((v, i) => `${t[i]}: ${v}`)
          .join('\n\n'),
      );
    });
  }

  async docx(): Promise<void> {
    await this.guard(async () => {
      const response = await this.api.invoke$Response(methodsResults, {
        project_id: this.projectId(),
        body: this.body(),
      });
      saveFile(
        response.body,
        fileNameFrom(response.headers.get('content-disposition'), 'draft.docx'),
      );
    });
  }

  async save(): Promise<void> {
    this.saved.set(false);
    await this.guard(async () => {
      const out = await this.api.invoke(saveAbstract, {
        project_id: this.projectId(),
        body: {
          text: this.text(),
          word_limit: this.wordLimit || null,
          char_limit: this.charLimit || null,
          version: this.version,
        },
      });
      this.version = out.version ?? null;
      this.saved.set(true);
    });
  }

  private async guard(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
    } catch (error) {
      this.error.set(await withJsonBody(error));
    } finally {
      this.busy.set(false);
    }
  }
}
