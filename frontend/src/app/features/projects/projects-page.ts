import { Component, OnInit, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { Skeleton } from '../../shared/skeleton';

import { LocalDatePipe } from '../../shared/local-date.pipe';
import { Api } from '../../core/api/api';
import { createProject } from '../../core/api/fn/projects/create-project';
import { listProjects } from '../../core/api/fn/projects/list-projects';
import { myUsage } from '../../core/api/fn/quotas/my-usage';
import { ProjectOut } from '../../core/api/models/project-out';
import { UsageItem } from '../../core/api/models/usage-item';
import { FormError } from '../../shared/form-error';
import { RestoreBackup } from './restore-backup';

@Component({
  selector: 'rm-projects-page',
  imports: [
    Skeleton,
    LocalDatePipe,
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    FormError,
    RestoreBackup,
  ],
  template: `
    <header class="page-header">
      <h1>{{ 'projects.title' | transloco }}</h1>
      @if (!creating()) {
        <button mat-flat-button type="button" (click)="creating.set(true)">
          {{ 'projects.new' | transloco }}
        </button>
      }
    </header>
    @if (usage(); as u) {
      <p class="muted">{{ 'projects.usage' | transloco: u }}</p>
    }

    @if (creating()) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h2>{{ 'projects.new' | transloco }}</h2></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <form [formGroup]="form" (ngSubmit)="create()" class="stack">
            <mat-form-field>
              <mat-label>{{ 'projects.projectTitle' | transloco }}</mat-label>
              <input matInput formControlName="title" />
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'projects.question' | transloco }}</mat-label>
              <textarea matInput formControlName="question" rows="3"></textarea>
              <mat-hint>{{ 'projects.questionHint' | transloco }}</mat-hint>
            </mat-form-field>
            <mat-form-field>
              <mat-label>{{ 'projects.deadline' | transloco }}</mat-label>
              <input matInput type="date" formControlName="deadline" />
            </mat-form-field>
            <rm-form-error [error]="error()" />
            <div class="actions">
              <button mat-button type="button" (click)="creating.set(false)">
                {{ 'common.cancel' | transloco }}
              </button>
              <button mat-flat-button type="submit" [disabled]="busy()">
                {{ 'projects.create' | transloco }}
              </button>
            </div>
          </form>
        </mat-card-content>
      </mat-card>
    }

    @if (loading()) {
      <rm-skeleton [lines]="[160, 160]" />
    } @else if (projects().length === 0) {
      <p class="empty">{{ 'projects.empty' | transloco }}</p>
    } @else {
      <div class="grid">
        @for (project of projects(); track project.id) {
          <mat-card class="project-card">
            <mat-card-content>
              <h2 class="project-card-title">
                <a [routerLink]="['/projetos', project.id]">{{ project.title }}</a>
              </h2>
              @if (project.archived_at) {
                <span class="pill pill-muted">{{ 'projects.archived' | transloco }}</span>
              }
              @if (project.question) {
                <p class="project-card-question">{{ project.question }}</p>
              }
              <div class="project-card-footer">
                @if (project.deadline) {
                  <span class="muted small">
                    {{ 'projects.deadline' | transloco }}: {{ project.deadline | localDate }}
                  </span>
                }
                <span class="tags" [attr.aria-label]="'projects.roles' | transloco">
                  @for (role of project.my_roles ?? []; track role) {
                    <span class="pill">{{ 'roles.' + role | transloco }}</span>
                  }
                </span>
              </div>
            </mat-card-content>
          </mat-card>
        }
      </div>
    }
    <details class="secondary-tools">
      <summary>{{ 'projects.moreTools' | transloco }}</summary>
      <rm-restore-backup (restored)="reload()" />
    </details>
  `,
})
export class ProjectsPage implements OnInit {
  private readonly api = inject(Api);

  protected readonly projects = signal<ProjectOut[]>([]);
  protected readonly usage = signal<UsageItem | null>(null);
  protected readonly loading = signal(true);
  protected readonly creating = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly form = inject(NonNullableFormBuilder).group({
    title: ['', Validators.required],
    question: [''],
    deadline: [''],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  protected async reload(): Promise<void> {
    this.loading.set(true);
    try {
      const [projects, usage] = await Promise.all([
        this.api.invoke(listProjects),
        this.api.invoke(myUsage),
      ]);
      this.projects.set(projects);
      this.usage.set(usage.projects);
    } finally {
      this.loading.set(false);
    }
  }

  async create(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    const value = this.form.getRawValue();
    try {
      await this.api.invoke(createProject, {
        body: {
          title: value.title,
          question: value.question || null,
          deadline: value.deadline || null,
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
