import { Component, effect, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { updateProject } from '../../core/api/fn/projects/update-project';
import { ProjectOut } from '../../core/api/models/project-out';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

const PICO = ['population', 'intervention', 'comparison', 'outcome'] as const;

/** Project details: title, question, PICO/PECO, PROSPERO, deadline and report language. */
@Component({
  selector: 'rm-project-details',
  imports: [
    ReactiveFormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <mat-card class="block">
      <mat-card-header>
        <mat-card-title
          ><h2>{{ 'details.title' | transloco }}</h2></mat-card-title
        >
      </mat-card-header>
      <mat-card-content>
        <rm-form-error [error]="error()" />
        @if (saved()) {
          <p class="notice notice-ok" role="status">{{ 'details.saved' | transloco }}</p>
        }
        <form [formGroup]="form" (ngSubmit)="save()" class="stack">
          <mat-form-field>
            <mat-label>{{ 'details.name' | transloco }}</mat-label>
            <input matInput formControlName="title" maxlength="300" />
          </mat-form-field>
          <mat-form-field>
            <mat-label>{{ 'details.question' | transloco }}</mat-label>
            <textarea matInput formControlName="question" rows="2" maxlength="5000"></textarea>
          </mat-form-field>
          <h3>
            PICO / PECO
            <span class="term" tabindex="0" [matTooltip]="'learning.terms.pico.text' | transloco"
              >?</span
            >
          </h3>
          <div class="mapping-grid" formGroupName="pico">
            @for (part of pico; track part) {
              <mat-form-field>
                <mat-label>{{ 'details.pico.' + part | transloco }}</mat-label>
                <textarea matInput [formControlName]="part" rows="2" maxlength="2000"></textarea>
              </mat-form-field>
            }
          </div>
          <h3>
            {{ 'details.confoundersTitle' | transloco }}
            <span
              class="term"
              tabindex="0"
              [matTooltip]="'learning.terms.confounding.text' | transloco"
              >?</span
            >
          </h3>
          <p class="muted small">{{ 'details.confoundersHelp' | transloco }}</p>
          <mat-form-field>
            <mat-label>{{ 'details.confounders' | transloco }}</mat-label>
            <textarea matInput formControlName="confounders" rows="3" maxlength="6000"></textarea>
            <mat-hint>{{ 'details.confoundersHint' | transloco }}</mat-hint>
          </mat-form-field>
          <div class="mapping-grid">
            <mat-form-field>
              <mat-label>{{ 'details.prospero' | transloco }}</mat-label>
              <input matInput formControlName="prospero" maxlength="64" />
              <mat-hint>{{ 'details.prosperoHint' | transloco }}</mat-hint>
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'details.deadline' | transloco }}</mat-label>
              <input matInput type="date" formControlName="deadline" />
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'details.reportLanguage' | transloco }}</mat-label>
              <mat-select formControlName="report_language">
                <mat-option value="pt-BR">{{ 'languages.pt-BR' | transloco }}</mat-option>
                <mat-option value="en">{{ 'languages.en' | transloco }}</mat-option>
              </mat-select>
            </mat-form-field>
          </div>
          @if (context.isAdmin()) {
            <div class="actions">
              <button mat-flat-button type="submit" [disabled]="busy() || form.pristine">
                {{ 'details.save' | transloco }}
              </button>
            </div>
          }
        </form>
      </mat-card-content>
    </mat-card>
  `,
})
export class ProjectDetails {
  private readonly api = inject(Api);
  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly context = inject(ProjectContext);

  protected readonly pico = PICO;
  protected readonly busy = signal(false);
  protected readonly saved = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly form = this.fb.group({
    title: ['', [Validators.required, Validators.maxLength(300)]],
    question: [''],
    pico: this.fb.group({ population: [''], intervention: [''], comparison: [''], outcome: [''] }),
    prospero: [''],
    deadline: [''],
    report_language: ['pt-BR' as 'pt-BR' | 'en'],
    confounders: [''],
  });

  constructor() {
    // Fill the form from the project, and again after it changes elsewhere.
    effect(() => {
      const project = this.context.project();
      if (project && this.form.pristine) this.fill(project);
    });
  }

  private fill(project: ProjectOut): void {
    const pico = (project.pico ?? {}) as Record<string, string | null | undefined>;
    this.form.reset({
      title: project.title,
      question: project.question ?? '',
      pico: Object.fromEntries(PICO.map((k) => [k, pico[k] ?? ''])) as Record<
        (typeof PICO)[number],
        string
      >,
      prospero: project.prospero ?? '',
      deadline: project.deadline ?? '',
      report_language: project.report_language === 'en' ? 'en' : 'pt-BR',
      confounders: (project.confounders ?? []).join('\n'),
    });
    if (this.context.isAdmin()) this.form.enable();
    else this.form.disable();
  }

  async save(): Promise<void> {
    const project = this.context.project();
    if (!project || this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    const text = (s: string): string | null => s.trim() || null;
    this.busy.set(true);
    this.error.set(null);
    this.saved.set(false);
    try {
      const updated = await this.api.invoke(updateProject, {
        project_id: project.id,
        body: {
          version: project.version,
          title: v.title.trim(),
          question: text(v.question),
          pico: {
            population: text(v.pico.population),
            intervention: text(v.pico.intervention),
            comparison: text(v.pico.comparison),
            outcome: text(v.pico.outcome),
          },
          prospero: text(v.prospero),
          deadline: v.deadline || null,
          report_language: v.report_language,
          confounders: [
            ...new Set(
              v.confounders
                .split('\n')
                .map((x) => x.trim())
                .filter(Boolean),
            ),
          ].slice(0, 30),
        },
      });
      this.form.markAsPristine();
      this.context.update(updated);
      this.fill(updated);
      this.saved.set(true);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
