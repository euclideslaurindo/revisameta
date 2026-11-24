import { Component, ElementRef, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { NgxExtendedPdfViewerModule, PageRenderedEvent } from 'ngx-extended-pdf-viewer';
import { firstValueFrom } from 'rxjs';

import { Api } from '../../core/api/api';
import { addArm } from '../../core/api/fn/extraction/add-arm';
import { deleteArm } from '../../core/api/fn/extraction/delete-arm';
import { direction } from '../../core/api/fn/extraction/direction';
import { getExtraction } from '../../core/api/fn/extraction/get-extraction';
import { listAlerts } from '../../core/api/fn/extraction/list-alerts';
import { getForm } from '../../core/api/fn/extraction/get-form';
import { setMeasure } from '../../core/api/fn/extraction/set-measure';
import { submitExtraction } from '../../core/api/fn/extraction/submit-extraction';
import { updateArm } from '../../core/api/fn/extraction/update-arm';
import { updateCharacteristics } from '../../core/api/fn/extraction/update-characteristics';
import { createAnnotation } from '../../core/api/fn/pdfs/create-annotation';
import { listAnnotations } from '../../core/api/fn/pdfs/list-annotations';
import { listPdfs } from '../../core/api/fn/pdfs/list-pdfs';
import { viewPdf } from '../../core/api/fn/pdfs/view-pdf';
import { listGroups } from '../../core/api/fn/protocol/list-groups';
import { listOutcomes } from '../../core/api/fn/protocol/list-outcomes';
import { getStudy } from '../../core/api/fn/studies/get-study';
import { AlertOut } from '../../core/api/models/alert-out';
import { AnnotationOut } from '../../core/api/models/annotation-out';
import { DirectionOut } from '../../core/api/models/direction-out';
import { ArmOut } from '../../core/api/models/arm-out';
import { ExtractionDetail } from '../../core/api/models/extraction-detail';
import { FormField } from '../../core/api/models/form-field';
import { GroupOut } from '../../core/api/models/group-out';
import { MeasureOut } from '../../core/api/models/measure-out';
import { OutcomeDataOut } from '../../core/api/models/outcome-data-out';
import { OutcomeOut } from '../../core/api/models/outcome-out';
import { PdfOut } from '../../core/api/models/pdf-out';
import { PdfViewOut } from '../../core/api/models/pdf-view-out';
import { StudyOut } from '../../core/api/models/study-out';
import { AuthService } from '../../core/auth/auth';
import { ConfirmDialog } from '../../shared/confirm-dialog';
import { FormError } from '../../shared/form-error';
import { isValidNumberText, parseDecimal, parseInteger } from '../../shared/numbers';
import { readPdfSelection } from '../pdfs/pdf-selection';
import { ProjectContext } from '../project/project-context';
import { AutosaveState } from './autosave';
import { paintAll, paintPage } from '../pdfs/pdf-highlights';
import { OutcomeRow } from './outcome-row';
import { AlertMessage } from './alert-message';
import { DirectionCheck } from './direction-check';

const SAVE_DELAY_MS = 800;

import { PlotDigitizer } from './plot-digitizer';

@Component({
  selector: 'rm-extraction-page',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoPipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    NgxExtendedPdfViewerModule,
    FormError,
    OutcomeRow,
    AlertMessage,
    DirectionCheck,
    PlotDigitizer,
  ],
  providers: [AutosaveState],
  template: `
    @if (extraction(); as ex) {
      <a [routerLink]="['/projetos', projectId(), 'estudos', ex.study_id]" class="back"
        >← {{ study()?.label }}</a
      >
      <header class="page-header sticky-status">
        <h2>{{ 'extraction.title' | transloco }} · {{ study()?.label }}</h2>
        <span class="save-status" [class]="'save-' + autosave.status()" role="status">
          {{ 'extraction.save.' + autosave.status() | transloco }}
        </span>
        @if (editable()) {
          <button mat-flat-button type="button" (click)="submit()">
            {{ 'extraction.submit' | transloco }}
          </button>
        } @else {
          <span class="badge">{{ 'extraction.status.' + ex.status | transloco }}</span>
        }
      </header>
      <rm-form-error [error]="autosave.error() ?? error()" />
      @if (ex.outdated_form) {
        <div class="notice notice-warn" role="status">
          {{ 'extraction.outdatedForm' | transloco }}
        </div>
      }

      <div class="extraction-layout">
        <section class="pdf-pane">
          @if (pdfs().length === 0) {
            <p class="empty">{{ 'extraction.noPdf' | transloco }}</p>
          } @else {
            @if (pdfs().length > 1) {
              <mat-form-field subscriptSizing="dynamic">
                <mat-label>PDF</mat-label>
                <mat-select [ngModel]="pdf()?.id" (ngModelChange)="openPdf($event)">
                  @for (p of pdfs(); track p.id) {
                    <mat-option [value]="p.id">{{ p.original_filename }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            }
            @if (pdf(); as p) {
              <ngx-extended-pdf-viewer
                [src]="p.url"
                [(page)]="page"
                [showOpenFileButton]="false"
                [showSecondaryToolbarButton]="false"
                [useInlineScripts]="false"
                height="70vh"
                (pageRendered)="onPageRendered($event)"
              />
              @if (editable()) {
                <div class="actions">
                  <button mat-stroked-button type="button" (click)="markPassage()">
                    {{ 'pdfs.annotations.mark' | transloco }}
                  </button>
                </div>
                @if (selectionMissing()) {
                  <p class="notice notice-warn" role="status">
                    {{ 'pdfs.annotations.selectFirst' | transloco }}
                  </p>
                }
              }
            }
          }
        </section>

        <section class="form-pane">
          <mat-card class="block">
            <mat-card-header>
              <mat-card-title>
                <h3>
                  {{ 'extraction.checks.title' | transloco }}
                  <span class="term" tabindex="0" [matTooltip]="'glossary.checks' | transloco"
                    >?</span
                  >
                </h3>
              </mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <p class="muted">
                {{
                  'extraction.checks.summary'
                    | transloco: { open: openAlerts(), justified: justifiedAlerts() }
                }}
              </p>
              @for (alert of generalAlerts(); track alert.id) {
                <rm-alert-message
                  [projectId]="projectId()"
                  [alert]="alert"
                  [canJustify]="editable()"
                />
              }
              <h4>{{ 'extraction.direction.title' | transloco }}</h4>
              <rm-direction-check
                [projectId]="projectId()"
                [extractionId]="ex.id"
                [studyLabel]="study()?.label ?? ''"
                [summaries]="directions()"
                [editable]="editable()"
                (changed)="directionChanged($event)"
              />
            </mat-card-content>
          </mat-card>

          <mat-card class="block">
            <mat-card-header
              ><mat-card-title
                ><h3>{{ 'extraction.characteristics' | transloco }}</h3></mat-card-title
              ></mat-card-header
            >
            <mat-card-content class="stack">
              @for (field of fields(); track field.key) {
                <mat-form-field subscriptSizing="dynamic">
                  <mat-label>{{
                    field.label_key ? (field.label_key | transloco) : field.label
                  }}</mat-label>
                  @switch (field.type) {
                    @case ('textarea') {
                      <textarea
                        matInput
                        rows="2"
                        [(ngModel)]="characteristics[field.key]"
                        (ngModelChange)="characteristicsChanged()"
                        [disabled]="!editable()"
                      ></textarea>
                    }
                    @case ('select') {
                      <mat-select
                        [(ngModel)]="characteristics[field.key]"
                        (ngModelChange)="characteristicsChanged()"
                        [disabled]="!editable()"
                      >
                        <mat-option [value]="null">—</mat-option>
                        @for (option of field.options ?? []; track option) {
                          <mat-option [value]="option">{{ option }}</mat-option>
                        }
                      </mat-select>
                    }
                    @case ('date') {
                      <input
                        matInput
                        type="date"
                        [(ngModel)]="characteristics[field.key]"
                        (ngModelChange)="characteristicsChanged()"
                        [disabled]="!editable()"
                      />
                    }
                    @default {
                      <input
                        matInput
                        [(ngModel)]="characteristics[field.key]"
                        (ngModelChange)="characteristicsChanged()"
                        [disabled]="!editable()"
                        [attr.inputmode]="field.type === 'number' ? 'decimal' : null"
                      />
                    }
                  }
                  @if (field.help) {
                    <mat-hint>{{ field.help }}</mat-hint>
                  }
                </mat-form-field>
              }
            </mat-card-content>
          </mat-card>

          <mat-card class="block">
            <mat-card-header>
              <mat-card-title>
                <h3>
                  {{ 'extraction.arms.title' | transloco }}
                  <span class="term" tabindex="0" [matTooltip]="'glossary.arm' | transloco">?</span>
                </h3>
              </mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <p class="muted">{{ 'extraction.arms.hint' | transloco }}</p>
              @for (arm of arms(); track arm.id) {
                <div class="row arm-row">
                  <mat-form-field subscriptSizing="dynamic">
                    <mat-label>{{ 'extraction.arms.label' | transloco }}</mat-label>
                    <input
                      matInput
                      [ngModel]="arm.label"
                      (ngModelChange)="armChanged(arm, { label: $event })"
                      [disabled]="!editable()"
                    />
                  </mat-form-field>
                  <mat-form-field subscriptSizing="dynamic">
                    <mat-label>n</mat-label>
                    <input
                      matInput
                      [ngModel]="arm.n"
                      (ngModelChange)="armChanged(arm, { n: $event })"
                      [disabled]="!editable()"
                      inputmode="numeric"
                    />
                  </mat-form-field>
                  <mat-form-field subscriptSizing="dynamic">
                    <mat-label>{{ 'extraction.arms.group' | transloco }}</mat-label>
                    <mat-select
                      [ngModel]="arm.mapped_group_id"
                      (ngModelChange)="armChanged(arm, { mapped_group_id: $event })"
                      [disabled]="!editable()"
                    >
                      <mat-option [value]="null">{{
                        'extraction.arms.noGroup' | transloco
                      }}</mat-option>
                      @for (g of groups(); track g.id) {
                        <mat-option [value]="g.id">{{ g.label }}</mat-option>
                      }
                    </mat-select>
                  </mat-form-field>
                  @if (editable()) {
                    <button mat-button type="button" (click)="removeArm(arm)">
                      {{ 'common.delete' | transloco }}
                    </button>
                  }
                </div>
              }
              @if (editable()) {
                <form class="row" (ngSubmit)="addArm()">
                  <mat-form-field subscriptSizing="dynamic">
                    <mat-label>{{ 'extraction.arms.new' | transloco }}</mat-label>
                    <input matInput name="newArm" [(ngModel)]="newArm" />
                  </mat-form-field>
                  <button mat-stroked-button type="submit">
                    {{ 'extraction.arms.add' | transloco }}
                  </button>
                </form>
              }
            </mat-card-content>
          </mat-card>

          @for (outcome of outcomes(); track outcome.id) {
            <mat-card class="block">
              <mat-card-header>
                <mat-card-title
                  ><h3>{{ outcome.name }}</h3></mat-card-title
                >
                <mat-card-subtitle>{{
                  'protocol.outcomes.types.' + outcome.type | transloco
                }}</mat-card-subtitle>
              </mat-card-header>
              <mat-card-content>
                @if (outcome.type === 'continuous') {
                  <div class="row">
                    <mat-form-field subscriptSizing="dynamic">
                      <mat-label>{{ 'extraction.scale.name' | transloco }}</mat-label>
                      <input
                        matInput
                        [ngModel]="scale(outcome).name"
                        (ngModelChange)="scaleChanged(outcome, { name: $event })"
                        [disabled]="!editable()"
                      />
                    </mat-form-field>
                    <mat-form-field subscriptSizing="dynamic">
                      <mat-label>{{ 'extraction.scale.min' | transloco }}</mat-label>
                      <input
                        matInput
                        [ngModel]="scale(outcome).min"
                        (ngModelChange)="scaleChanged(outcome, { min: $event })"
                        [disabled]="!editable()"
                        inputmode="decimal"
                      />
                    </mat-form-field>
                    <mat-form-field subscriptSizing="dynamic">
                      <mat-label>{{ 'extraction.scale.max' | transloco }}</mat-label>
                      <input
                        matInput
                        [ngModel]="scale(outcome).max"
                        (ngModelChange)="scaleChanged(outcome, { max: $event })"
                        [disabled]="!editable()"
                        inputmode="decimal"
                      />
                    </mat-form-field>
                    <mat-checkbox
                      [ngModel]="scale(outcome).higherIsBetter"
                      (ngModelChange)="scaleChanged(outcome, { higherIsBetter: $event })"
                      [disabled]="!editable()"
                    >
                      {{ 'protocol.outcomes.higherBetter' | transloco }}
                    </mat-checkbox>
                  </div>
                }
                @if (outcome.timepoints.length === 0) {
                  <p class="notice notice-warn">{{ 'extraction.noTimepoints' | transloco }}</p>
                } @else if (arms().length === 0) {
                  <p class="muted">{{ 'extraction.addArmsFirst' | transloco }}</p>
                }
                @for (timepoint of outcome.timepoints; track timepoint) {
                  @for (arm of arms(); track arm.id) {
                    <rm-outcome-row
                      [projectId]="projectId()"
                      [extractionId]="ex.id"
                      [outcomeId]="outcome.id"
                      [dichotomous]="outcome.type === 'dichotomous'"
                      [armId]="arm.id"
                      [armLabel]="arm.label"
                      [timepoint]="timepoint"
                      [row]="rowFor(outcome.id, arm.id, timepoint)"
                      [annotations]="annotations()"
                      [editable]="editable()"
                      [alerts]="alertsFor(outcome.id, arm.id, timepoint)"
                      (saved)="rowSaved($event)"
                    />
                  }
                }
              </mat-card-content>
            </mat-card>
          }
        </section>
      </div>
    } @else {
      <rm-form-error [error]="error()" />
    }
    <details class="block">
      <summary>{{ 'digitizer.open' | transloco }}</summary>
      <rm-plot-digitizer />
    </details>
  `,
})
export class ExtractionPage {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  private readonly auth = inject(AuthService);
  protected readonly context = inject(ProjectContext);
  protected readonly autosave = inject(AutosaveState);

  readonly extractionId = input.required<string>();
  protected readonly extraction = signal<ExtractionDetail | null>(null);
  protected readonly study = signal<StudyOut | null>(null);
  protected readonly fields = signal<FormField[]>([]);
  protected readonly outcomes = signal<OutcomeOut[]>([]);
  protected readonly groups = signal<GroupOut[]>([]);
  protected readonly arms = signal<ArmOut[]>([]);
  protected readonly pdfs = signal<PdfOut[]>([]);
  protected readonly pdf = signal<PdfViewOut | null>(null);
  private readonly host = inject(ElementRef<HTMLElement>);
  /** Passages of the PDF on screen (the list holds those of every PDF of the study). */
  private readonly pagePassages = computed(() => {
    const id = this.pdf()?.id;
    return this.annotations().filter((a) => a.pdf_file_id === id);
  });
  protected readonly annotations = signal<AnnotationOut[]>([]);
  protected readonly error = signal<unknown>(null);
  protected readonly selectionMissing = signal(false);
  protected readonly alerts = signal<AlertOut[]>([]);
  protected readonly directions = signal<DirectionOut[]>([]);
  protected readonly generalAlerts = computed(() =>
    this.alerts().filter((a) => a.target_type !== 'row'),
  );
  protected readonly openAlerts = computed(
    () => this.alerts().filter((a) => a.status === 'open').length,
  );
  protected readonly justifiedAlerts = computed(
    () => this.alerts().filter((a) => a.status === 'justified').length,
  );
  protected readonly editable = computed(() => {
    const ex = this.extraction();
    if (!ex || ex.status !== 'draft') return false;
    return ex.kind === 'consensus'
      ? this.context.isAdmin()
      : ex.extractor_id === this.auth.user()?.id;
  });
  protected page = 1;
  protected newArm = '';
  protected characteristics: Record<string, unknown> = {};
  private rows: OutcomeDataOut[] = [];
  private measures = new Map<string, MeasureOut>();
  private scales = new Map<
    string,
    { name: string; min: string; max: string; higherIsBetter: boolean }
  >();
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  // One save at a time per item, so versions never race each other.
  private queues = new Map<string, Promise<void>>();

  protected onPageRendered(event: PageRenderedEvent): void {
    paintPage(this.host.nativeElement, event.pageNumber, this.pagePassages());
  }

  constructor() {
    effect(() => paintAll(this.host.nativeElement, this.pagePassages()));
    effect(() => void this.load(this.extractionId()));
    // After every save, recompute the safeguards (alerts and direction sentences).
    effect(() => {
      if (this.autosave.saved() > 0) void this.reloadChecks();
    });
  }

  private async reloadChecks(): Promise<void> {
    const ex = this.extraction();
    if (!ex) return;
    const params = { project_id: this.projectId(), extraction_id: ex.id };
    const [alerts, directions] = await Promise.all([
      this.api.invoke(listAlerts, params),
      this.api.invoke(direction, params),
    ]);
    this.alerts.set(alerts);
    this.directions.set(directions);
  }

  protected alertsFor(outcomeId: string, armId: string, timepoint: string): AlertOut[] {
    const row = this.rowFor(outcomeId, armId, timepoint);
    return row
      ? this.alerts().filter((a) => a.target_type === 'row' && a.target_id === row.id)
      : [];
  }

  protected async directionChanged(summaries: DirectionOut[]): Promise<void> {
    this.directions.set(summaries);
    const ex = this.extraction();
    if (!ex) return;
    // Confirming bumps the rows on the server: take their new versions.
    const detail = await this.api.invoke(getExtraction, {
      project_id: this.projectId(),
      extraction_id: ex.id,
    });
    this.rows = detail.outcome_data;
    await this.reloadChecks();
  }

  protected projectId(): string {
    return this.context.project()!.id;
  }

  private async load(extractionId: string): Promise<void> {
    const project_id = this.projectId();
    try {
      const [ex, form, outcomes, groups] = await Promise.all([
        this.api.invoke(getExtraction, { project_id, extraction_id: extractionId }),
        this.api.invoke(getForm, { project_id }),
        this.api.invoke(listOutcomes, { project_id }),
        this.api.invoke(listGroups, { project_id }),
      ]);
      this.characteristics = { ...ex.characteristics };
      this.rows = ex.outcome_data;
      this.measures = new Map(ex.measures.map((m) => [m.outcome_id, m]));
      this.fields.set(form.schema.fields);
      this.outcomes.set(outcomes);
      this.groups.set(groups);
      this.arms.set(ex.arms);
      this.extraction.set(ex);
      await this.reloadChecks();
      const study = await this.api.invoke(getStudy, { project_id, study_id: ex.study_id });
      this.study.set(study);
      const pdfLists = await Promise.all(
        study.reports.map((r) => this.api.invoke(listPdfs, { project_id, report_id: r.id })),
      );
      const pdfs = pdfLists.flat();
      this.pdfs.set(pdfs);
      await this.reloadAnnotations();
      if (pdfs.length) await this.openPdf(pdfs[0].id);
    } catch (error) {
      this.error.set(error);
    }
  }

  private async reloadAnnotations(): Promise<void> {
    const lists = await Promise.all(
      this.pdfs().map((p) =>
        this.api.invoke(listAnnotations, { project_id: this.projectId(), pdf_id: p.id }),
      ),
    );
    this.annotations.set(lists.flat());
  }

  async openPdf(pdfId: string): Promise<void> {
    this.pdf.set(await this.api.invoke(viewPdf, { project_id: this.projectId(), pdf_id: pdfId }));
  }

  async markPassage(): Promise<void> {
    const selection = readPdfSelection();
    this.selectionMissing.set(!selection);
    const pdf = this.pdf();
    if (!selection || !pdf) return;
    await this.autosave.track(() =>
      this.api.invoke(createAnnotation, {
        project_id: this.projectId(),
        pdf_id: pdf.id,
        body: selection,
      }),
    );
    window.getSelection()?.removeAllRanges();
    await this.reloadAnnotations();
  }

  private debounce(key: string, action: () => Promise<void>): void {
    this.autosave.markDirty();
    const previous = this.timers.get(key);
    if (previous) clearTimeout(previous);
    this.timers.set(
      key,
      setTimeout(() => {
        const next = (this.queues.get(key) ?? Promise.resolve()).then(action);
        this.queues.set(key, next);
      }, SAVE_DELAY_MS),
    );
  }

  characteristicsChanged(): void {
    this.debounce('characteristics', async () => {
      const ex = this.extraction();
      if (!ex) return;
      const result = await this.autosave.track(() =>
        this.api.invoke(updateCharacteristics, {
          project_id: this.projectId(),
          extraction_id: ex.id,
          body: { version: ex.version, characteristics: this.characteristics },
        }),
      );
      if (result)
        this.extraction.set({
          ...ex,
          version: result.version,
          outdated_form: result.outdated_form,
        });
    });
  }

  armChanged(
    arm: ArmOut,
    change: { label?: string; n?: string | number | null; mapped_group_id?: string | null },
  ): void {
    if (
      change.n !== undefined &&
      !isValidNumberText(change.n === null ? '' : String(change.n), true)
    ) {
      this.autosave.error.set(null);
      return;
    }
    const patch = {
      ...(change.label !== undefined ? { label: change.label } : {}),
      ...(change.n !== undefined ? { n: parseInteger(change.n) } : {}),
      ...(change.mapped_group_id !== undefined ? { mapped_group_id: change.mapped_group_id } : {}),
    };
    this.debounce(`arm-${arm.id}`, async () => {
      const latest = this.arms().find((a) => a.id === arm.id) ?? arm;
      const updated = await this.autosave.track(() =>
        this.api.invoke(updateArm, {
          project_id: this.projectId(),
          arm_id: arm.id,
          body: { version: latest.version, ...patch },
        }),
      );
      if (updated) this.arms.update((list) => list.map((a) => (a.id === updated.id ? updated : a)));
    });
  }

  async addArm(): Promise<void> {
    const ex = this.extraction();
    if (!ex || !this.newArm.trim()) return;
    const arm = await this.autosave.track(() =>
      this.api.invoke(addArm, {
        project_id: this.projectId(),
        extraction_id: ex.id,
        body: { label: this.newArm.trim(), position: this.arms().length },
      }),
    );
    if (arm) {
      this.arms.update((list) => [...list, arm]);
      this.newArm = '';
    }
  }

  async removeArm(arm: ArmOut): Promise<void> {
    const ok = await firstValueFrom(
      this.dialog
        .open(ConfirmDialog, {
          data: { message: 'extraction.arms.confirmDelete', params: { label: arm.label } },
        })
        .afterClosed(),
    );
    if (!ok) return;
    const done = await this.autosave.track(async () => {
      await this.api.invoke(deleteArm, { project_id: this.projectId(), arm_id: arm.id });
      return true;
    });
    if (done) this.arms.update((list) => list.filter((a) => a.id !== arm.id));
  }

  scale(outcome: OutcomeOut): { name: string; min: string; max: string; higherIsBetter: boolean } {
    let scale = this.scales.get(outcome.id);
    if (!scale) {
      const m = this.measures.get(outcome.id);
      scale = {
        name: m?.scale_name ?? '',
        min: m?.scale_min != null ? String(m.scale_min).replace('.', ',') : '',
        max: m?.scale_max != null ? String(m.scale_max).replace('.', ',') : '',
        higherIsBetter: m?.higher_is_better ?? outcome.higher_is_better,
      };
      this.scales.set(outcome.id, scale);
    }
    return scale;
  }

  scaleChanged(
    outcome: OutcomeOut,
    change: Partial<{ name: string; min: string; max: string; higherIsBetter: boolean }>,
  ): void {
    const scale = { ...this.scale(outcome), ...change };
    this.scales.set(outcome.id, scale);
    if (!isValidNumberText(scale.min) || !isValidNumberText(scale.max)) return;
    this.debounce(`scale-${outcome.id}`, async () => {
      const ex = this.extraction();
      if (!ex) return;
      const saved = await this.autosave.track(() =>
        this.api.invoke(setMeasure, {
          project_id: this.projectId(),
          extraction_id: ex.id,
          outcome_id: outcome.id,
          body: {
            scale_name: scale.name || null,
            scale_min: parseDecimal(scale.min),
            scale_max: parseDecimal(scale.max),
            higher_is_better: scale.higherIsBetter,
          },
        }),
      );
      if (saved) this.measures.set(outcome.id, saved);
    });
  }

  rowFor(outcomeId: string, armId: string, timepoint: string): OutcomeDataOut | null {
    return (
      this.rows.find(
        (r) => r.outcome_id === outcomeId && r.arm_id === armId && r.timepoint === timepoint,
      ) ?? null
    );
  }

  rowSaved(row: OutcomeDataOut): void {
    this.rows = [...this.rows.filter((r) => r.id !== row.id), row];
  }

  async submit(): Promise<void> {
    const ex = this.extraction();
    if (!ex) return;
    const ok = await firstValueFrom(
      this.dialog
        .open(ConfirmDialog, { data: { message: 'extraction.confirmSubmit' } })
        .afterClosed(),
    );
    if (!ok) return;
    const result = await this.autosave.track(() =>
      this.api.invoke(submitExtraction, { project_id: this.projectId(), extraction_id: ex.id }),
    );
    if (result) this.extraction.set({ ...ex, status: result.status, version: result.version });
  }
}
