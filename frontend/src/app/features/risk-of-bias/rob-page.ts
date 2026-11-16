import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { enableRobTool } from '../../core/api/fn/risk-of-bias/enable-rob-tool';
import { listRobTools } from '../../core/api/fn/risk-of-bias/list-rob-tools';
import { robAgreement } from '../../core/api/fn/risk-of-bias/rob-agreement';
import { robCatalog } from '../../core/api/fn/risk-of-bias/rob-catalog';
import { CatalogItem } from '../../core/api/models/catalog-item';
import { RobProjectAgreementOut } from '../../core/api/models/rob-project-agreement-out';
import { ToolOut } from '../../core/api/models/tool-out';
import { FormError } from '../../shared/form-error';
import { displayDecimal } from '../../shared/numbers';
import { ProjectContext } from '../project/project-context';
import { RobRuleEditor } from './rob-rule-editor';
import { RobToolEditor, localized } from './rob-tool-editor';

/** Risk of bias: the instruments of the project (step 1 of stage 2). */
@Component({
  selector: 'rm-rob-page',
  imports: [
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatTooltipModule,
    FormError,
    RobToolEditor,
    RobRuleEditor,
  ],
  template: `
    <p class="muted">
      {{ 'rob.intro' | transloco }}
      <span class="term" tabindex="0" [matTooltip]="'glossary.riskOfBias' | transloco">?</span>
    </p>
    <rm-form-error [error]="error()" />
    @if (tools().length) {
      <p>
        <a mat-flat-button [routerLink]="['/projetos', projectId(), 'risco-de-vies', 'tabela']">
          {{ 'rob.table.open' | transloco }}
        </a>
        @if (isAdmin()) {
          <a
            mat-stroked-button
            [routerLink]="['/projetos', projectId(), 'risco-de-vies', 'importar']"
          >
            {{ 'rob.import.open' | transloco }}
          </a>
        }
      </p>
    }

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
                @if (isGroupRule(t)) {
                  <div class="muted">
                    {{ (t.overall_rule ? 'rob.rule.defined' : 'rob.rule.none') | transloco }}
                  </div>
                }
                @if (ruleEditing() === t.id) {
                  <rm-rob-rule-editor
                    [projectId]="projectId()"
                    [tool]="t"
                    (saved)="replace($event)"
                    (closed)="ruleEditing.set(null)"
                  />
                }
                @if (editing() === t.id) {
                  <rm-rob-tool-editor
                    [projectId]="projectId()"
                    [tool]="t"
                    (saved)="replace($event)"
                    (closed)="editing.set(null)"
                  />
                }
              </div>
              @if (isAdmin() && isGroupRule(t) && ruleEditing() !== t.id) {
                <button mat-stroked-button type="button" (click)="ruleEditing.set(t.id)">
                  {{ 'rob.rule.edit' | transloco }}
                </button>
              }
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

    @if (agreement(); as g) {
      <mat-card class="block">
        <mat-card-header>
          <mat-card-title
            ><h3>
              {{ 'rob.agreement.title' | transloco }}
              <span class="term" tabindex="0" [matTooltip]="'glossary.robKappa' | transloco"
                >?</span
              >
            </h3></mat-card-title
          >
        </mat-card-header>
        <mat-card-content>
          @if (g.agreement; as a) {
            <p>
              {{
                'rob.agreement.summary'
                  | transloco
                    : {
                        pairs: g.pairs,
                        percent: number(a.agreement_percent, 1),
                        agreeing: a.agreeing_items,
                        items: a.items,
                      }
              }}
              @if (a.kappa !== null && a.kappa !== undefined) {
                · {{ 'rob.consensus.kappa' | transloco: { kappa: number(a.kappa, 2) } }}
              }
            </p>
          } @else if (g.agreement_error) {
            <p class="notice notice-error">{{ 'consensus.agreement.unavailable' | transloco }}</p>
          } @else {
            <p class="muted">{{ 'rob.agreement.none' | transloco }}</p>
          }
        </mat-card-content>
      </mat-card>
    }

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
  protected readonly agreement = signal<RobProjectAgreementOut | null>(null);
  protected readonly editing = signal<string | null>(null);
  protected readonly ruleEditing = signal<string | null>(null);
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
      this.agreement.set(await this.api.invoke(robAgreement, { project_id }));
    } catch (error) {
      this.error.set(error);
    }
  }

  protected number(value: number, digits: number): string {
    return displayDecimal(value.toFixed(digits), this.lang());
  }

  protected name(value: unknown): string {
    return localized(value as Record<string, string>, this.lang());
  }

  protected isGroupRule(tool: ToolOut): boolean {
    return (tool.structure['judgement'] as { kind?: string } | undefined)?.kind === 'group_rule';
  }

  protected replace(tool: ToolOut): void {
    this.tools.update((list) => list.map((t) => (t.id === tool.id ? tool : t)));
    this.editing.set(null);
    this.ruleEditing.set(null);
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
