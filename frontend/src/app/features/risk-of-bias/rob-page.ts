import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { enableRobTool } from '../../core/api/fn/risk-of-bias/enable-rob-tool';
import { listRobTools } from '../../core/api/fn/risk-of-bias/list-rob-tools';
import { robCatalog } from '../../core/api/fn/risk-of-bias/rob-catalog';
import { CatalogItem } from '../../core/api/models/catalog-item';
import { ToolOut } from '../../core/api/models/tool-out';
import { FormError } from '../../shared/form-error';
import { ProjectContext } from '../project/project-context';
import { RobToolEditor, localized } from './rob-tool-editor';

/** Risk of bias: the instruments of the project (step 1 of stage 2). */
@Component({
  selector: 'rm-rob-page',
  imports: [
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatTooltipModule,
    FormError,
    RobToolEditor,
  ],
  template: `
    <p class="muted">
      {{ 'rob.intro' | transloco }}
      <span class="term" tabindex="0" [matTooltip]="'glossary.riskOfBias' | transloco">?</span>
    </p>
    <rm-form-error [error]="error()" />

    <mat-card class="block">
      <mat-card-header>
        <mat-card-title
          ><h3>{{ 'rob.tools.title' | transloco }}</h3></mat-card-title
        >
      </mat-card-header>
      <mat-card-content>
        @if (tools().length === 0) {
          <p class="empty">{{ 'rob.tools.empty' | transloco }}</p>
        }
        <ul class="item-list">
          @for (t of tools(); track t.id) {
            <li class="stack-item">
              <div>
                <strong>{{ name(t.structure['name']) }}</strong>
                <span class="badge">{{
                  'rob.version' | transloco: { version: t.template_version }
                }}</span>
                <div class="muted">{{ t.structure['citation'] }}</div>
                <div class="muted">
                  {{
                    'rob.tools.textsFilled'
                      | transloco: { filled: t.texts_filled, total: t.questions }
                  }}
                </div>
                @if (editing() === t.id) {
                  <rm-rob-tool-editor
                    [projectId]="projectId()"
                    [tool]="t"
                    (saved)="replace($event)"
                    (closed)="editing.set(null)"
                  />
                }
              </div>
              @if (isAdmin() && editing() !== t.id) {
                <button mat-stroked-button type="button" (click)="editing.set(t.id)">
                  {{
                    (t.family === 'generic' ? 'rob.tools.configure' : 'rob.tools.pasteTexts')
                      | transloco
                  }}
                </button>
              }
            </li>
          }
        </ul>
      </mat-card-content>
    </mat-card>

    @if (isAdmin()) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>{{ 'rob.catalog.title' | transloco }}</h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          <p class="muted">{{ 'rob.catalog.hint' | transloco }}</p>
          <ul class="item-list">
            @for (c of available(); track c.key) {
              <li>
                <div>
                  <strong>{{ name(c.name) }}</strong>
                  <span class="badge">{{ 'rob.version' | transloco: { version: c.version } }}</span>
                  <div class="muted">
                    {{
                      'rob.catalog.size' | transloco: { domains: c.domains, questions: c.questions }
                    }}
                    · {{ 'rob.scope.' + c.scope | transloco }}
                  </div>
                  @if (c.citation) {
                    <div class="muted">{{ c.citation }}</div>
                  }
                  @if (c.source_url) {
                    <a [href]="c.source_url" target="_blank" rel="noopener">{{
                      'rob.catalog.source' | transloco
                    }}</a>
                  }
                </div>
                <button mat-flat-button type="button" [disabled]="busy()" (click)="enable(c)">
                  {{ 'rob.catalog.enable' | transloco }}
                </button>
              </li>
            }
          </ul>
          @if (available().length === 0) {
            <p class="muted">{{ 'rob.catalog.allEnabled' | transloco }}</p>
          }
        </mat-card-content>
      </mat-card>
    }
  `,
})
export class RobPage implements OnInit {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  private readonly lang = toSignal(inject(TranslocoService).langChanges$, {
    initialValue: 'pt-BR',
  });

  protected readonly catalog = signal<CatalogItem[]>([]);
  protected readonly tools = signal<ToolOut[]>([]);
  protected readonly editing = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly isAdmin = computed(() => this.context.isAdmin());
  protected readonly projectId = computed(() => this.context.project()!.id);
  protected readonly available = computed(() => {
    const enabled = new Set(this.tools().map((t) => `${t.template_key}@${t.template_version}`));
    return this.catalog().filter((c) => !enabled.has(`${c.key}@${c.version}`));
  });

  async ngOnInit(): Promise<void> {
    try {
      const project_id = this.projectId();
      const [catalog, tools] = await Promise.all([
        this.api.invoke(robCatalog, { project_id }),
        this.api.invoke(listRobTools, { project_id }),
      ]);
      this.catalog.set(catalog);
      this.tools.set(tools);
    } catch (error) {
      this.error.set(error);
    }
  }

  protected name(value: unknown): string {
    return localized(value as Record<string, string>, this.lang());
  }

  protected replace(tool: ToolOut): void {
    this.tools.update((list) => list.map((t) => (t.id === tool.id ? tool : t)));
    this.editing.set(null);
  }

  async enable(item: CatalogItem): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const tool = await this.api.invoke(enableRobTool, {
        project_id: this.projectId(),
        body: { template_key: item.key },
      });
      this.tools.update((list) => [...list, tool]);
    } catch (error) {
      this.error.set(error);
    } finally {
      this.busy.set(false);
    }
  }
}
