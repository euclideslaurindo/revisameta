import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { createStudy } from '../../core/api/fn/studies/create-study';
import { listStudies } from '../../core/api/fn/studies/list-studies';
import { StudyDesign } from '../../core/api/models/study-design';
import { StudyOut } from '../../core/api/models/study-out';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { STUDY_DESIGNS } from './designs';

@Component({
  selector: 'rm-studies-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTableModule,
    MatTooltipModule,
    FormError,
  ],
  template: `
    <header class="page-header">
      <p class="muted">
        {{ 'studies.intro' | transloco }}
        <span class="term" tabindex="0" [matTooltip]="'glossary.studyVsReport' | transloco">?</span>
      </p>
      @if (canEdit()) {
        <div class="actions">
          <a mat-stroked-button routerLink="importar">{{ 'studies.import' | transloco }}</a>
          <a mat-stroked-button routerLink="importar-extracao">{{
            'studies.importExtraction' | transloco
          }}</a>
          @if (!creating()) {
            <button mat-flat-button type="button" (click)="creating.set(true)">
              {{ 'studies.new' | transloco }}
            </button>
          }
        </div>
      }
    </header>

    @if (creating()) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h2>{{ 'studies.new' | transloco }}</h2></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <form [formGroup]="form" (ngSubmit)="create()" class="stack">
            <mat-form-field>
              <mat-label>{{ 'studies.label' | transloco }}</mat-label>
              <input matInput formControlName="label" />
              <mat-hint>{{ 'studies.labelHint' | transloco }}</mat-hint>
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'studies.design' | transloco }}</mat-label>
              <mat-select formControlName="design">
                @for (design of designs; track design) {
                  <mat-option [value]="design">{{ 'designs.' + design | transloco }}</mat-option>
                }
              </mat-select>
              <mat-hint>{{ 'studies.designHint' | transloco }}</mat-hint>
            </mat-form-field>
            <h3>{{ 'studies.mainArticle' | transloco }}</h3>
            <mat-form-field>
              <mat-label>{{ 'references.title' | transloco }}</mat-label>
              <input matInput formControlName="title" />
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'references.authors' | transloco }}</mat-label>
              <input matInput formControlName="authors" />
            </mat-form-field>
            <div class="row">
              <mat-form-field>
                <mat-label>{{ 'references.year' | transloco }}</mat-label>
                <input matInput type="number" formControlName="year" />
              </mat-form-field>
              <mat-form-field>
                <mat-label>DOI</mat-label>
                <input matInput formControlName="doi" />
              </mat-form-field>
            </div>
            <rm-form-error [error]="error()" />
            <div class="actions">
              <button mat-button type="button" (click)="creating.set(false)">
                {{ 'common.cancel' | transloco }}
              </button>
              <button mat-flat-button type="submit" [disabled]="busy()">
                {{ 'studies.create' | transloco }}
              </button>
            </div>
          </form>
        </mat-card-content>
      </mat-card>
    }

    @if (studies().length === 0) {
      <p class="empty">{{ 'studies.empty' | transloco }}</p>
    } @else {
      <table mat-table [dataSource]="studies()" class="full-table">
        <ng-container matColumnDef="label">
          <th mat-header-cell *matHeaderCellDef>{{ 'studies.label' | transloco }}</th>
          <td mat-cell *matCellDef="let study">
            <a [routerLink]="study.id">{{ study.label }}</a>
          </td>
        </ng-container>
        <ng-container matColumnDef="design">
          <th mat-header-cell *matHeaderCellDef>{{ 'studies.design' | transloco }}</th>
          <td mat-cell *matCellDef="let study">{{ 'designs.' + study.design | transloco }}</td>
        </ng-container>
        <ng-container matColumnDef="article">
          <th mat-header-cell *matHeaderCellDef>{{ 'studies.mainArticle' | transloco }}</th>
          <td mat-cell *matCellDef="let study">{{ primaryTitle(study) }}</td>
        </ng-container>
        <ng-container matColumnDef="reports">
          <th mat-header-cell *matHeaderCellDef>{{ 'studies.articles' | transloco }}</th>
          <td mat-cell *matCellDef="let study">{{ study.reports.length }}</td>
        </ng-container>
        <tr mat-header-row *matHeaderRowDef="columns"></tr>
        <tr mat-row *matRowDef="let row; columns: columns"></tr>
      </table>
    }
  `,
})
export class StudiesPage implements OnInit {
  private readonly api = inject(Api);
  protected readonly context = inject(ProjectContext);
  protected readonly designs = STUDY_DESIGNS;
  protected readonly columns = ['label', 'design', 'article', 'reports'];

  protected readonly studies = signal<StudyOut[]>([]);
  protected readonly creating = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly canEdit = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.includes('admin') || roles.includes('extractor');
  });

  protected readonly form = inject(NonNullableFormBuilder).group({
    label: ['', Validators.required],
    design: ['cohort_retrospective' as StudyDesign, Validators.required],
    title: ['', Validators.required],
    authors: [''],
    year: [null as number | null],
    doi: [''],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.studies.set(
      await this.api.invoke(listStudies, { project_id: this.context.project()!.id }),
    );
  }

  protected primaryTitle(study: StudyOut): string {
    const ref = (study.reports.find((r) => r.is_primary) ?? study.reports[0])?.reference;
    return ref ? `${ref.title}${ref.year ? ` (${ref.year})` : ''}` : '';
  }

  async create(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.invoke(createStudy, {
        project_id: this.context.project()!.id,
        body: {
          label: value.label,
          design: value.design,
          reference: {
            title: value.title,
            authors: value.authors || null,
            year: value.year || null,
            doi: value.doi || null,
          },
        },
      });
      this.form.reset();
      this.creating.set(false);
      await this.reload();
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
