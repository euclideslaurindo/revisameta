import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { prismaChecklist } from '../../core/api/fn/prisma/prisma-checklist';
import { prismaChecklistDocx } from '../../core/api/fn/prisma/prisma-checklist-docx';
import { recordChecklistItem } from '../../core/api/fn/prisma/record-checklist-item';
import { ChecklistOut } from '../../core/api/models/checklist-out';
import { ChecklistRow } from '../../core/api/models/checklist-row';
import { withJsonBody } from '../../core/errors/problem';
import { fileNameFrom, saveFile } from '../../shared/download';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';

interface Draft {
  status: string;
  location: string;
}

/** PRISMA 2020 checklist: where the manuscript reports each item. */
@Component({
  selector: 'rm-prisma-checklist',
  imports: [
    FormsModule,
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
      <mat-card-content>
        <h3>
          {{
            (kind() === 'abstracts' ? 'prisma.checklist.titleAbstracts' : 'prisma.checklist.title')
              | transloco
          }}
          <span class="term" tabindex="0" [matTooltip]="'prisma.checklist.help' | transloco"
            >?</span
          >
        </h3>
        <rm-form-error [error]="error()" />
        @if (data(); as d) {
          <p>
            {{
              'prisma.checklist.summary'
                | transloco: { reported: d.reported, na: d.not_applicable, pending: d.pending }
            }}
          </p>
          <p class="muted">
            {{ 'prisma.checklist.source' | transloco }}
            <a [href]="d.source" target="_blank" rel="noopener noreferrer">{{ d.source }}</a>.
            {{ d.citation }}
          </p>
          <div class="actions">
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="docx()">
              {{ 'prisma.checklist.docx' | transloco }}
            </button>
          </div>
          <table class="result-table">
            <thead>
              <tr>
                <th scope="col">{{ 'prisma.checklist.item' | transloco }}</th>
                <th scope="col">{{ 'prisma.checklist.what' | transloco }}</th>
                <th scope="col">{{ 'prisma.checklist.where' | transloco }}</th>
              </tr>
            </thead>
            <tbody>
              @for (r of d.rows; track r.code) {
                @if (r.section !== previous(r)) {
                  <tr>
                    <th colspan="3" scope="colgroup">
                      {{ 'prisma.checklist.section.' + r.section | transloco }}
                    </th>
                  </tr>
                }
                <tr>
                  <td>
                    <strong>{{ r.code }}</strong> {{ r.topic[lang()] }}
                    @if (r.has_data && r.status === 'pending') {
                      <div>
                        <span class="badge">{{ 'prisma.checklist.hasData' | transloco }}</span>
                      </div>
                    }
                  </td>
                  <td>{{ r.summary[lang()] }}</td>
                  <td>
                    @if (canEdit()) {
                      <div class="row">
                        <mat-form-field subscriptSizing="dynamic" class="status">
                          <mat-label>{{ 'prisma.checklist.status' | transloco }}</mat-label>
                          <mat-select [(ngModel)]="draft(r).status">
                            @for (s of statuses; track s) {
                              <mat-option [value]="s">{{
                                'prisma.checklist.statusName.' + s | transloco
                              }}</mat-option>
                            }
                          </mat-select>
                        </mat-form-field>
                        <mat-form-field subscriptSizing="dynamic">
                          <mat-label>{{ 'prisma.checklist.location' | transloco }}</mat-label>
                          <input matInput maxlength="500" [(ngModel)]="draft(r).location" />
                        </mat-form-field>
                        <button mat-button type="button" [disabled]="busy()" (click)="save(r)">
                          {{ 'prisma.save' | transloco }}
                        </button>
                      </div>
                    } @else {
                      {{ 'prisma.checklist.statusName.' + r.status | transloco }}
                      @if (r.location) {
                        — {{ r.location }}
                      }
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .status {
      width: 160px;
    }
  `,
})
export class PrismaChecklist implements OnInit {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  private readonly context = inject(ProjectContext);

  /** prisma2020 (27 items) or abstracts (PRISMA for Abstracts, 12 items). */
  readonly kind = input<'prisma2020' | 'abstracts'>('prisma2020');

  protected readonly statuses = ['pending', 'reported', 'not_applicable'];
  protected readonly data = signal<ChecklistOut | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly lang = computed<'pt-BR' | 'en'>(() =>
    this.transloco.getActiveLang().startsWith('en') ? 'en' : 'pt-BR',
  );
  protected readonly canEdit = computed(() => {
    const roles = this.context.project()?.my_roles ?? [];
    return roles.some((r) => r !== 'reader');
  });
  private drafts = new Map<string, Draft>();

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    await this.guard(() => this.load());
  }

  private async load(): Promise<void> {
    this.drafts.clear();
    this.data.set(
      await this.api.invoke(prismaChecklist, { project_id: this.projectId(), kind: this.kind() }),
    );
  }

  protected previous(r: ChecklistRow): string | null {
    const rows = this.data()?.rows ?? [];
    const i = rows.indexOf(r);
    return i > 0 ? rows[i - 1].section : null;
  }

  protected draft(r: ChecklistRow): Draft {
    let d = this.drafts.get(r.code);
    if (!d) {
      d = { status: r.status, location: r.location ?? '' };
      this.drafts.set(r.code, d);
    }
    return d;
  }

  async save(r: ChecklistRow): Promise<void> {
    const d = this.draft(r);
    await this.guard(async () => {
      await this.api.invoke(recordChecklistItem, {
        project_id: this.projectId(),
        code: r.code,
        body: {
          status: d.status as 'pending' | 'reported' | 'not_applicable',
          location: d.location.trim() || null,
          version: r.version ?? null,
        },
      });
      await this.load();
    });
  }

  async docx(): Promise<void> {
    await this.guard(async () => {
      const response = await this.api.invoke$Response(prismaChecklistDocx, {
        project_id: this.projectId(),
        lang: this.lang(),
        kind: this.kind(),
      });
      saveFile(
        response.body,
        fileNameFrom(response.headers.get('content-disposition'), 'prisma-checklist.docx'),
      );
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
