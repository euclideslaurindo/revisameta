import { Component, computed, effect, inject, input, signal } from '@angular/core';
import {
  FormsModule,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { Api } from '../../core/api/api';
import { addReport } from '../../core/api/fn/studies/add-report';
import { deleteStudy } from '../../core/api/fn/studies/delete-study';
import { getStudy } from '../../core/api/fn/studies/get-study';
import { listStudies } from '../../core/api/fn/studies/list-studies';
import { mergeStudies } from '../../core/api/fn/studies/merge-studies';
import { removeReport } from '../../core/api/fn/studies/remove-report';
import { updateStudy } from '../../core/api/fn/studies/update-study';
import { ReportOut } from '../../core/api/models/report-out';
import { StudyDesign } from '../../core/api/models/study-design';
import { StudyOut } from '../../core/api/models/study-out';
import { ConfirmData, ConfirmDialog } from '../../shared/confirm-dialog';
import { FormError } from '../../shared/form-error';
import { StudyExtractions } from '../extraction/study-extractions';
import { CommentsPanel } from '../../shared/comments-panel';
import { ReportPdfs } from '../pdfs/report-pdfs';
import { StudyRobTool } from '../risk-of-bias/study-rob-tool';
import { ProjectContext } from '../project/project-context';
import { STUDY_DESIGNS } from './designs';

@Component({
  selector: 'rm-study-page',
  imports: [
    StudyRobTool,
    FormsModule,
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    FormError,
    ReportPdfs,
    StudyExtractions,
    CommentsPanel,
  ],
  template: `
    <a routerLink=".." class="back">← {{ 'project.nav.studies' | transloco }}</a>
    <rm-form-error [error]="error()" />
    @if (study(); as s) {
      <header class="page-header">
        <h2>{{ s.label }}</h2>
        @if (context.isAdmin()) {
          <button mat-button type="button" (click)="remove(s)">
            {{ 'studies.delete' | transloco }}
          </button>
        }
      </header>

      <mat-card class="block">
        <mat-card-content class="stack">
          <mat-form-field>
            <mat-label>{{ 'studies.design' | transloco }}</mat-label>
            <mat-select
              [value]="s.design"
              [disabled]="!canEdit()"
              (valueChange)="changeDesign(s, $event)"
            >
              @for (design of designs; track design) {
                <mat-option [value]="design">{{ 'designs.' + design | transloco }}</mat-option>
              }
            </mat-select>
            <mat-hint>{{ 'studies.designHint' | transloco }}</mat-hint>
          </mat-form-field>
        </mat-card-content>
      </mat-card>

      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>{{ 'rob.study.title' | transloco }}</h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <rm-study-rob-tool [studyId]="s.id" />
        </mat-card-content>
      </mat-card>

      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>{{ 'extraction.title' | transloco }}</h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <rm-study-extractions [studyId]="s.id" />
        </mat-card-content>
      </mat-card>

      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>{{ 'comments.title' | transloco }}</h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <rm-comments-panel entity="study" [entityId]="s.id" />
        </mat-card-content>
      </mat-card>

      <mat-card class="block">
        <mat-card-header>
          <mat-card-title>
            <h3>
              {{ 'studies.articles' | transloco }}
              <span class="term" tabindex="0" [matTooltip]="'glossary.studyVsReport' | transloco"
                >?</span
              >
            </h3>
          </mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <ul class="item-list">
            @for (report of s.reports; track report.id) {
              <li>
                <div>
                  <strong>{{ report.reference.title }}</strong>
                  @if (report.is_primary) {
                    <span class="badge">{{ 'studies.primary' | transloco }}</span>
                  }
                  <div class="muted">
                    {{ report.reference.authors }}
                    @if (report.reference.year) {
                      · {{ report.reference.year }}
                    }
                    @if (report.reference.doi) {
                      · DOI {{ report.reference.doi }}
                    }
                  </div>
                  <rm-report-pdfs
                    [projectId]="projectId()"
                    [reportId]="report.id"
                    [canUpload]="canUploadPdf()"
                  />
                </div>
                @if (canEdit() && s.reports.length > 1) {
                  <button mat-button type="button" (click)="removeArticle(s, report)">
                    {{ 'common.delete' | transloco }}
                  </button>
                }
              </li>
            }
          </ul>

          @if (canEdit()) {
            <form [formGroup]="articleForm" (ngSubmit)="addArticle(s)" class="stack">
              <h4>{{ 'studies.addArticle' | transloco }}</h4>
              <p class="muted">{{ 'studies.addArticleHint' | transloco }}</p>
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
              <div class="actions">
                <button mat-flat-button type="submit" [disabled]="busy()">
                  {{ 'studies.addArticle' | transloco }}
                </button>
              </div>
            </form>
          }
        </mat-card-content>
      </mat-card>

      @if (canEdit() && others().length > 0) {
        <mat-card class="block">
          <mat-card-header>
            <mat-card-title
              ><h3>{{ 'studies.merge.title' | transloco }}</h3></mat-card-title
            >
          </mat-card-header>
          <mat-card-content class="stack">
            <p class="muted">{{ 'studies.merge.hint' | transloco }}</p>
            <mat-form-field>
              <mat-label>{{ 'studies.merge.other' | transloco }}</mat-label>
              <mat-select [(ngModel)]="mergeTarget">
                @for (other of others(); track other.id) {
                  <mat-option [value]="other.id">{{ other.label }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <div class="actions">
              <button
                mat-stroked-button
                type="button"
                [disabled]="!mergeTarget || busy()"
                (click)="merge(s)"
              >
                {{ 'studies.merge.action' | transloco }}
              </button>
            </div>
          </mat-card-content>
        </mat-card>
      }
    }
  `,
})
export class StudyPage {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  protected readonly context = inject(ProjectContext);
  protected readonly designs = STUDY_DESIGNS;

  readonly studyId = input.required<string>();
  protected readonly study = signal<StudyOut | null>(null);
  protected readonly others = signal<StudyOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected mergeTarget: string | null = null;
  protected readonly canEdit = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.includes('admin') || roles.includes('extractor');
  });
  protected readonly canUploadPdf = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.some((r) => r === 'admin' || r === 'reviewer' || r === 'extractor');
  });

  protected readonly articleForm = inject(NonNullableFormBuilder).group({
    title: ['', Validators.required],
    authors: [''],
    year: [null as number | null],
    doi: [''],
  });

  constructor() {
    effect(() => void this.load(this.studyId()));
  }

  protected projectId(): string {
    return this.context.project()!.id;
  }

  private async load(studyId: string): Promise<void> {
    try {
      const [study, all] = await Promise.all([
        this.api.invoke(getStudy, { project_id: this.projectId(), study_id: studyId }),
        this.api.invoke(listStudies, { project_id: this.projectId() }),
      ]);
      this.study.set(study);
      this.others.set(all.filter((s) => s.id !== studyId));
    } catch (error) {
      this.error.set(error);
    }
  }

  private async run(action: () => Promise<StudyOut | void>): Promise<boolean> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const result = await action();
      if (result) this.study.set(result);
      return true;
    } catch (error) {
      this.error.set(error);
      return false;
    } finally {
      this.busy.set(false);
    }
  }

  private async confirm(data: ConfirmData): Promise<boolean> {
    return (await firstValueFrom(this.dialog.open(ConfirmDialog, { data }).afterClosed())) === true;
  }

  async changeDesign(study: StudyOut, design: StudyDesign): Promise<void> {
    await this.run(() =>
      this.api.invoke(updateStudy, {
        project_id: this.projectId(),
        study_id: study.id,
        body: { version: study.version, design },
      }),
    );
  }

  async addArticle(study: StudyOut): Promise<void> {
    if (this.articleForm.invalid) {
      this.articleForm.markAllAsTouched();
      return;
    }
    const value = this.articleForm.getRawValue();
    const ok = await this.run(() =>
      this.api.invoke(addReport, {
        project_id: this.projectId(),
        study_id: study.id,
        body: {
          reference: {
            title: value.title,
            authors: value.authors || null,
            year: value.year || null,
            doi: value.doi || null,
          },
        },
      }),
    );
    if (ok) this.articleForm.reset();
  }

  async removeArticle(study: StudyOut, report: ReportOut): Promise<void> {
    if (
      !(await this.confirm({
        message: 'studies.confirmRemoveArticle',
        params: { title: report.reference.title },
      }))
    )
      return;
    await this.run(() =>
      this.api.invoke(removeReport, {
        project_id: this.projectId(),
        study_id: study.id,
        report_id: report.id,
      }),
    );
  }

  async merge(study: StudyOut): Promise<void> {
    const other = this.others().find((s) => s.id === this.mergeTarget);
    if (!other) return;
    if (
      !(await this.confirm({
        message: 'studies.merge.confirm',
        params: { other: other.label, study: study.label },
      }))
    )
      return;
    const ok = await this.run(() =>
      this.api.invoke(mergeStudies, {
        project_id: this.projectId(),
        study_id: study.id,
        body: { other_study_id: other.id },
      }),
    );
    if (ok) {
      this.mergeTarget = null;
      this.others.update((list) => list.filter((s) => s.id !== other.id));
    }
  }

  async remove(study: StudyOut): Promise<void> {
    if (!(await this.confirm({ message: 'studies.confirmDelete', params: { label: study.label } })))
      return;
    const ok = await this.run(() =>
      this.api.invoke(deleteStudy, { project_id: this.projectId(), study_id: study.id }),
    );
    if (ok) await this.router.navigate(['/projetos', this.projectId(), 'estudos']);
  }
}
