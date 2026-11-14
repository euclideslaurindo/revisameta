import { Component, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatRadioModule } from '@angular/material/radio';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Api } from '../../core/api/api';
import { getRobAssessment } from '../../core/api/fn/risk-of-bias/get-rob-assessment';
import { listRobTools } from '../../core/api/fn/risk-of-bias/list-rob-tools';
import { saveRobAnswers } from '../../core/api/fn/risk-of-bias/save-rob-answers';
import { setRobJudgement } from '../../core/api/fn/risk-of-bias/set-rob-judgement';
import { setRobVariants } from '../../core/api/fn/risk-of-bias/set-rob-variants';
import { submitRobAssessment } from '../../core/api/fn/risk-of-bias/submit-rob-assessment';
import { getStudy } from '../../core/api/fn/studies/get-study';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { AnnotationOut } from '../../core/api/models/annotation-out';
import { AnswerIn } from '../../core/api/models/answer-in';
import { AnswerOut } from '../../core/api/models/answer-out';
import { AssessmentOut } from '../../core/api/models/assessment-out';
import { DomainState } from '../../core/api/models/domain-state';
import { JudgementIn } from '../../core/api/models/judgement-in';
import { ToolOut } from '../../core/api/models/tool-out';
import { AuthService } from '../../core/auth/auth';
import { FormError } from '../../shared/form-error';
import { StudyPdfPane } from '../pdfs/study-pdf-pane';
import { ProjectContext } from '../project/project-context';
import { AutosaveState } from '../extraction/autosave';
import { RobJudgement } from './rob-judgement';
import { AnswerSlot, RobQuestion } from './rob-question';
import { localized } from './rob-tool-editor';

interface TemplateQuestion {
  key: string;
  label?: string;
  variant?: string;
  answers: string;
  level: 'study' | 'outcome' | 'result';
}
interface TemplateDomain {
  key: string;
  name: Record<string, string>;
  questions: TemplateQuestion[];
  variants?: { key: string; name: Record<string, string> }[];
}
interface TemplateView {
  name: Record<string, string>;
  scope: 'study' | 'result';
  answer_sets: Record<string, string[]>;
  judgement: { kind: string; levels: string[]; direction: string[] };
  domains: TemplateDomain[];
}

/**
 * Risk-of-bias assessment of one study (or one result), with the article beside it.
 * Answers save as they are given; the suggested judgements follow them.
 */
@Component({
  selector: 'rm-rob-assessment-page',
  providers: [AutosaveState],
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatRadioModule,
    MatTooltipModule,
    FormError,
    StudyPdfPane,
    RobJudgement,
    RobQuestion,
  ],
  template: `
    @if (assessment(); as a) {
      <a [routerLink]="['/projetos', projectId(), 'estudos', a.study_id]">← {{ studyLabel() }}</a>
      <header class="page-header sticky-status">
        <h2>
          {{ 'rob.assessment.title' | transloco: { study: studyLabel() } }}
          <span class="term" tabindex="0" [matTooltip]="'glossary.riskOfBias' | transloco">?</span>
        </h2>
        <span class="badge">{{ 'extraction.status.' + a.status | transloco }}</span>
        <span class="save-status" [class]="'save-' + autosaveStatus()" role="status">{{
          'extraction.save.' + autosaveStatus() | transloco
        }}</span>
      </header>
      <p class="muted">
        {{ toolName() }} ({{ 'rob.version' | transloco: { version: a.template_version } }})
        @if (a.timepoint) {
          · {{ outcomeName(a.outcome_id) }} · {{ a.timepoint }}
        }
        @if (a.reviewer_name) {
          · {{ a.reviewer_name }}
        }
      </p>
      <rm-form-error [error]="error()" />

      <div class="extraction-layout">
        <section class="pdf-pane">
          <rm-study-pdf-pane
            [projectId]="projectId()"
            [studyId]="a.study_id"
            [canMark]="editable()"
            (annotationsChange)="annotations.set($event)"
          />
        </section>

        <section class="form-pane">
          @for (domain of template()?.domains ?? []; track domain.key) {
            @let state = domainState(domain.key);
            <mat-card class="block">
              <mat-card-header>
                <mat-card-title
                  ><h3>{{ name(domain.name) }}</h3></mat-card-title
                >
              </mat-card-header>
              <mat-card-content>
                @if (domain.variants?.length) {
                  <p class="muted">{{ 'rob.assessment.chooseVariant' | transloco }}</p>
                  <mat-radio-group
                    class="stack"
                    [ngModel]="a.variants[domain.key] ?? null"
                    (ngModelChange)="setVariant(domain.key, $event)"
                    [disabled]="!editable()"
                  >
                    @for (v of domain.variants; track v.key) {
                      <mat-radio-button [value]="v.key">{{ name(v.name) }}</mat-radio-button>
                    }
                  </mat-radio-group>
                }
                @for (question of visibleQuestions(domain, state); track question.key) {
                  <div class="rob-question-block">
                    <h4>
                      {{ 'rob.texts.question' | transloco: { n: question.label ?? question.key } }}
                      <span class="muted"
                        >· {{ 'rob.level.' + levelOf(question) | transloco }}</span
                      >
                    </h4>
                    @if (text(domain.key, question.key); as t) {
                      <p>{{ t }}</p>
                    } @else {
                      <p class="muted">{{ 'rob.assessment.noText' | transloco }}</p>
                    }
                    @for (
                      slot of slots(domain.key, question);
                      track slot.outcomeId + '|' + slot.timepoint
                    ) {
                      <rm-rob-question
                        [slot]="slot"
                        [options]="optionsOf(question)"
                        [label]="question.label ?? question.key"
                        [current]="answerFor(slot)"
                        [annotations]="annotations()"
                        [editable]="editable()"
                        (changed)="saveAnswer($event)"
                        (showPassage)="pdfPane()?.show($event)"
                      />
                    }
                  </div>
                }
                @if (hasDomainJudgements() && state) {
                  <h4>{{ 'rob.assessment.domainJudgement' | transloco }}</h4>
                  <rm-rob-judgement
                    [domainKey]="domain.key"
                    [label]="'rob.assessment.judgement' | transloco"
                    [state]="state"
                    [levels]="template()?.judgement?.levels ?? []"
                    [directions]="template()?.judgement?.direction ?? []"
                    [editable]="editable()"
                    [showNoSuggestion]="a.judgement_kind === 'algorithm'"
                    [levelLabel]="levelLabel"
                    (changed)="saveJudgement($event)"
                  />
                }
              </mat-card-content>
            </mat-card>
          }

          <mat-card class="block">
            <mat-card-header>
              <mat-card-title
                ><h3>{{ 'rob.assessment.overall' | transloco }}</h3></mat-card-title
              >
            </mat-card-header>
            <mat-card-content>
              @if (a.judgement_kind === 'group_rule' && !a.overall.suggested) {
                <p class="muted">{{ 'rob.assessment.groupRuleHint' | transloco }}</p>
              }
              @for (w of a.overall.warnings; track w) {
                <div class="alert-item">{{ 'rob.warning.' + w | transloco }}</div>
              }
              <rm-rob-judgement
                [label]="'rob.assessment.overallJudgement' | transloco"
                [state]="a.overall"
                [levels]="a.overall.levels"
                [directions]="template()?.judgement?.direction ?? []"
                [editable]="editable()"
                [levelLabel]="levelLabel"
                (changed)="saveJudgement($event)"
              />
            </mat-card-content>
          </mat-card>

          <mat-card class="block">
            <mat-card-content>
              @if (a.missing.length) {
                <p>{{ 'rob.assessment.missing' | transloco: { count: a.missing.length } }}</p>
                <ul>
                  @for (m of a.missing.slice(0, 12); track m) {
                    <li>{{ missingText(m) }}</li>
                  }
                </ul>
              } @else if (a.status === 'draft') {
                <p>{{ 'rob.assessment.ready' | transloco }}</p>
              }
              @if (editable()) {
                <button mat-flat-button type="button" [disabled]="busy()" (click)="submit()">
                  {{ 'rob.assessment.submit' | transloco }}
                </button>
              }
            </mat-card-content>
          </mat-card>
        </section>
      </div>
    } @else {
      <rm-form-error [error]="error()" />
    }
  `,
})
export class RobAssessmentPage {
  private readonly api = inject(Api);
  private readonly context = inject(ProjectContext);
  private readonly auth = inject(AuthService);
  private readonly autosave = inject(AutosaveState);
  private readonly transloco = inject(TranslocoService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: 'pt-BR' });

  readonly assessmentId = input.required<string>();
  protected readonly pdfPane = viewChild(StudyPdfPane);

  protected readonly assessment = signal<AssessmentOut | null>(null);
  protected readonly tool = signal<ToolOut | null>(null);
  protected readonly studyLabel = signal('');
  protected readonly annotations = signal<AnnotationOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  private readonly outcomes = signal<Record<string, string>>({});

  protected readonly projectId = computed(() => this.context.project()!.id);
  protected readonly template = computed(() => this.tool()?.structure as TemplateView | undefined);
  protected readonly hasDomainJudgements = computed(() => {
    const kind = this.assessment()?.judgement_kind;
    return kind === 'algorithm' || kind === 'reviewer';
  });
  protected readonly editable = computed(() => {
    const a = this.assessment();
    if (!a || a.status !== 'draft') return false;
    return a.kind === 'individual'
      ? a.reviewer_id === this.auth.user()?.id
      : this.context.isAdmin();
  });
  protected readonly autosaveStatus = computed(() => this.autosave.status());

  constructor() {
    effect(() => void this.load(this.assessmentId()));
  }

  private t = (key: string, params?: Record<string, unknown>) => {
    this.lang();
    return this.transloco.translate(key, params);
  };

  /** Official levels are translated; levels named by the group are shown as typed. */
  protected levelLabel = (level: string): string => {
    const key = 'rob.judgement.' + level;
    const text = this.t(key);
    return text === key ? level : text;
  };

  protected name(value: Record<string, string>): string {
    return localized(value, this.lang());
  }

  protected toolName(): string {
    return this.template() ? this.name(this.template()!.name) : '';
  }

  protected outcomeName(id: string | null | undefined): string {
    return id ? (this.outcomes()[id] ?? '') : '';
  }

  protected domainState(key: string): DomainState | undefined {
    return this.assessment()?.domains.find((d) => d.domain_key === key);
  }

  protected visibleQuestions(
    domain: TemplateDomain,
    state: DomainState | undefined,
  ): TemplateQuestion[] {
    const asked = new Set(state?.asked ?? []);
    return domain.questions.filter((q) => asked.has(q.key));
  }

  protected levelOf(question: TemplateQuestion): string {
    return this.template()?.scope === 'study' ? question.level : 'result';
  }

  protected text(domainKey: string, questionKey: string): string | undefined {
    return this.tool()?.texts?.[`${domainKey}.${questionKey}`];
  }

  protected optionsOf(question: TemplateQuestion): string[] {
    return this.template()?.answer_sets[question.answers] ?? [];
  }

  protected slots(domainKey: string, question: TemplateQuestion): AnswerSlot[] {
    const questionKey = `${domainKey}.${question.key}`;
    const level = this.template()?.scope === 'study' ? question.level : 'study';
    if (level === 'study')
      return [{ questionKey, outcomeId: null, timepoint: null, targetLabel: null }];
    const out: AnswerSlot[] = [];
    for (const t of this.assessment()?.targets ?? []) {
      if (level === 'outcome') {
        out.push({
          questionKey,
          outcomeId: t.outcome_id,
          timepoint: null,
          targetLabel: t.outcome_name,
        });
      } else {
        for (const point of t.timepoints) {
          out.push({
            questionKey,
            outcomeId: t.outcome_id,
            timepoint: point,
            targetLabel: `${t.outcome_name} · ${point}`,
          });
        }
      }
    }
    return out;
  }

  protected answerFor(slot: AnswerSlot): AnswerOut | null {
    return (
      this.assessment()?.answers.find(
        (x) =>
          x.question_key === slot.questionKey &&
          (x.outcome_id ?? null) === slot.outcomeId &&
          (x.timepoint ?? null) === slot.timepoint,
      ) ?? null
    );
  }

  protected missingText(code: string): string {
    const [kind, rest] = code.split(':');
    if (kind === 'answer') {
      const [domainKey, ...q] = rest.split('.');
      const domain = this.template()?.domains.find((d) => d.key === domainKey);
      const question = domain?.questions.find((x) => x.key === q.join('.'));
      return this.t('rob.missing.answer', {
        question: question?.label ?? q.join('.'),
        domain: domain ? this.name(domain.name) : domainKey,
      });
    }
    const domain = this.template()?.domains.find((d) => d.key === rest);
    const domainName = domain ? this.name(domain.name) : rest;
    if (kind === 'justification' && rest === 'overall')
      return this.t('rob.missing.justificationOverall');
    return this.t('rob.missing.' + kind, { domain: domainName });
  }

  private async load(id: string): Promise<void> {
    const project_id = this.projectId();
    try {
      const a = await this.api.invoke(getRobAssessment, { project_id, assessment_id: id });
      const [tools, study, outcomes] = await Promise.all([
        this.api.invoke(listRobTools, { project_id }),
        this.api.invoke(getStudy, { project_id, study_id: a.study_id }),
        this.api.invoke(listOutcomes, { project_id }),
      ]);
      this.tool.set(tools.find((t) => t.id === a.tool_id) ?? null);
      this.studyLabel.set(study.label);
      this.outcomes.set(Object.fromEntries(outcomes.map((o) => [o.id, o.name])));
      this.assessment.set(a);
    } catch (error) {
      this.error.set(error);
    }
  }

  private async run(action: () => Promise<AssessmentOut>): Promise<void> {
    const result = await this.autosave.track(action);
    if (result) this.assessment.set(result);
    this.error.set(this.autosave.error());
  }

  protected saveAnswer(answer: AnswerIn): void {
    void this.run(() =>
      this.api.invoke(saveRobAnswers, {
        project_id: this.projectId(),
        assessment_id: this.assessmentId(),
        body: { answers: [answer] },
      }),
    );
  }

  protected setVariant(domainKey: string, variant: string): void {
    void this.run(() =>
      this.api.invoke(setRobVariants, {
        project_id: this.projectId(),
        assessment_id: this.assessmentId(),
        body: { variants: { [domainKey]: variant } },
      }),
    );
  }

  protected saveJudgement(judgement: JudgementIn): void {
    void this.run(() =>
      this.api.invoke(setRobJudgement, {
        project_id: this.projectId(),
        assessment_id: this.assessmentId(),
        body: judgement,
      }),
    );
  }

  async submit(): Promise<void> {
    this.busy.set(true);
    await this.run(() =>
      this.api.invoke(submitRobAssessment, {
        project_id: this.projectId(),
        assessment_id: this.assessmentId(),
      }),
    );
    this.busy.set(false);
  }
}
