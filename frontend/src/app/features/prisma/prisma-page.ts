import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { adjustPrismaCount } from '../../core/api/fn/prisma/adjust-prisma-count';
import { prismaCounts } from '../../core/api/fn/prisma/prisma-counts';
import { prismaFlowDiagram } from '../../core/api/fn/prisma/prisma-flow-diagram';
import { prismaFlowDocx } from '../../core/api/fn/prisma/prisma-flow-docx';
import { PrismaCounts } from '../../core/api/models/prisma-counts';
import { withJsonBody } from '../../core/errors/problem';
import { fileNameFrom, saveFile } from '../../shared/download';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { PrismaChecklist } from './prisma-checklist';

const KEYS = [
  'identified_total',
  'duplicates_removed',
  'records_screened',
  'records_excluded',
  'reports_sought',
  'reports_not_retrieved',
  'reports_assessed',
  'reports_excluded_total',
  'studies_included',
  'reports_included',
  'studies_meta_analysis',
] as const;
type Key = (typeof KEYS)[number];

/** PRISMA 2020 flow diagram with the counts of the system and manual adjustments. */
@Component({
  selector: 'rm-prisma-page',
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
    PrismaChecklist,
  ],
  template: `
    <h2>
      {{ 'prisma.title' | transloco }}
      <span class="term" tabindex="0" [matTooltip]="'prisma.help' | transloco">?</span>
    </h2>
    <p class="muted">{{ 'prisma.intro' | transloco }}</p>
    <rm-form-error [error]="error()" />

    @if (counts(); as c) {
      @for (w of c.warnings; track w) {
        <p class="notice notice-warn" role="status">{{ 'prisma.warning.' + w | transloco }}</p>
      }
    }

    <div class="row">
      <mat-form-field subscriptSizing="dynamic">
        <mat-label>{{ 'rob.plots.lang' | transloco }}</mat-label>
        <mat-select [(ngModel)]="lang" (ngModelChange)="draw()">
          <mat-option value="pt-BR">Português</mat-option>
          <mat-option value="en">English</mat-option>
        </mat-select>
      </mat-form-field>
      <button mat-stroked-button type="button" [disabled]="busy()" (click)="download('svg')">
        {{ 'rob.plots.downloadSvg' | transloco }}
      </button>
      <button mat-stroked-button type="button" [disabled]="busy()" (click)="download('png')">
        {{ 'rob.plots.downloadPng' | transloco }}
      </button>
      <button mat-stroked-button type="button" [disabled]="busy()" (click)="downloadDocx()">
        {{ 'prisma.docx' | transloco }}
      </button>
    </div>
    @if (url(); as u) {
      <img class="rob-plot" [src]="u" [alt]="'prisma.title' | transloco" />
    }

    @if (counts(); as c) {
      <mat-card class="block">
        <mat-card-content>
          <h3>{{ 'prisma.counts' | transloco }}</h3>
          <table class="result-table">
            <thead>
              <tr>
                <th scope="col">{{ 'prisma.count' | transloco }}</th>
                <th scope="col">{{ 'prisma.system' | transloco }}</th>
                <th scope="col">{{ 'prisma.used' | transloco }}</th>
                @if (context.isAdmin()) {
                  <th scope="col">{{ 'prisma.adjust' | transloco }}</th>
                }
              </tr>
            </thead>
            <tbody>
              @for (k of keys; track k) {
                <tr>
                  <td>
                    {{ 'prisma.key.' + k | transloco }}
                    @if (c.adjusted[k]; as a) {
                      <div class="muted">
                        {{ 'prisma.why' | transloco: { text: a.justification } }}
                      </div>
                    }
                  </td>
                  <td>{{ c.computed[k] }}</td>
                  <td>
                    <strong>{{ c.values[k] }}</strong>
                    @if (c.adjusted[k]) {
                      <span class="badge">{{ 'prisma.adjusted' | transloco }}</span>
                    }
                  </td>
                  @if (context.isAdmin()) {
                    <td>
                      @if (editing === k) {
                        <div class="row">
                          <mat-form-field subscriptSizing="dynamic" class="num">
                            <mat-label>{{ 'prisma.value' | transloco }}</mat-label>
                            <input matInput type="number" min="0" [(ngModel)]="value" />
                          </mat-form-field>
                          <mat-form-field subscriptSizing="dynamic">
                            <mat-label>{{ 'prisma.justification' | transloco }}</mat-label>
                            <input matInput maxlength="1000" [(ngModel)]="justification" />
                          </mat-form-field>
                          <button mat-button type="button" [disabled]="busy()" (click)="save(k)">
                            {{ 'prisma.save' | transloco }}
                          </button>
                        </div>
                      } @else {
                        <button mat-button type="button" (click)="edit(k, c)">
                          {{ 'prisma.adjust' | transloco }}
                        </button>
                        @if (c.adjusted[k]) {
                          <button mat-button type="button" [disabled]="busy()" (click)="clear(k)">
                            {{ 'prisma.useSystem' | transloco }}
                          </button>
                        }
                      }
                    </td>
                  }
                </tr>
              }
            </tbody>
          </table>
        </mat-card-content>
      </mat-card>
    }

    <rm-prisma-checklist />
  `,
  styles: `
    .num {
      width: 110px;
    }
  `,
})
export class PrismaPage implements OnInit, OnDestroy {
  private readonly api = inject(Api);
  private readonly transloco = inject(TranslocoService);
  protected readonly context = inject(ProjectContext);

  protected readonly keys = KEYS;
  protected readonly counts = signal<PrismaCounts | null>(null);
  protected readonly url = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected lang: 'pt-BR' | 'en' = 'pt-BR';
  protected editing: Key | null = null;
  protected value: number | null = null;
  protected justification = '';

  private projectId(): string {
    return this.context.project()!.id;
  }

  async ngOnInit(): Promise<void> {
    this.lang = this.transloco.getActiveLang().startsWith('en') ? 'en' : 'pt-BR';
    await this.guard(async () => {
      this.counts.set(await this.api.invoke(prismaCounts, { project_id: this.projectId() }));
      await this.render();
    });
  }

  ngOnDestroy(): void {
    const u = this.url();
    if (u) URL.revokeObjectURL(u);
  }

  private async render(): Promise<void> {
    const response = await this.api.invoke$Response(prismaFlowDiagram, {
      project_id: this.projectId(),
      body: { format: 'svg', lang: this.lang },
    });
    const old = this.url();
    if (old) URL.revokeObjectURL(old);
    this.url.set(URL.createObjectURL(response.body));
  }

  async draw(): Promise<void> {
    await this.guard(() => this.render());
  }

  async download(format: 'svg' | 'png'): Promise<void> {
    await this.guard(async () => {
      const response = await this.api.invoke$Response(prismaFlowDiagram, {
        project_id: this.projectId(),
        body: { format, lang: this.lang },
      });
      saveFile(
        response.body,
        fileNameFrom(response.headers.get('content-disposition'), `prisma.${format}`),
      );
    });
  }

  async downloadDocx(): Promise<void> {
    await this.guard(async () => {
      const response = await this.api.invoke$Response(prismaFlowDocx, {
        project_id: this.projectId(),
        lang: this.lang,
      });
      saveFile(
        response.body,
        fileNameFrom(response.headers.get('content-disposition'), 'prisma.docx'),
      );
    });
  }

  protected edit(key: Key, c: PrismaCounts): void {
    this.editing = key;
    this.value = c.values[key] ?? 0;
    this.justification = c.adjusted[key]?.justification ?? '';
  }

  async save(key: Key): Promise<void> {
    await this.guard(async () => {
      this.counts.set(
        await this.api.invoke(adjustPrismaCount, {
          project_id: this.projectId(),
          key,
          body: { value: Number(this.value), justification: this.justification.trim() },
        }),
      );
      this.editing = null;
      await this.render();
    });
  }

  async clear(key: Key): Promise<void> {
    await this.guard(async () => {
      this.counts.set(
        await this.api.invoke(adjustPrismaCount, {
          project_id: this.projectId(),
          key,
          body: { value: null },
        }),
      );
      await this.render();
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
