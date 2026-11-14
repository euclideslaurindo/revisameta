import { Component, computed, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { TranslocoPipe } from '@jsverse/transloco';

import { AnnotationOut } from '../../core/api/models/annotation-out';
import { AnswerIn } from '../../core/api/models/answer-in';
import { AnswerOut } from '../../core/api/models/answer-out';

/** One answer slot: a question for the study, for an outcome or for one result. */
export interface AnswerSlot {
  questionKey: string;
  outcomeId: string | null;
  timepoint: string | null;
  targetLabel: string | null;
}

/** Answer of one signalling question, with justification and the passage that supports it. */
@Component({
  selector: 'rm-rob-question',
  imports: [
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
  ],
  template: `
    <div class="rob-question">
      @if (slot().targetLabel) {
        <div class="muted">{{ slot().targetLabel }}</div>
      }
      <mat-button-toggle-group
        [value]="current()?.answer ?? null"
        (change)="save({ answer: $event.value })"
        [disabled]="!editable()"
        [attr.aria-label]="label()"
        class="rob-answers"
      >
        @for (option of options(); track option) {
          <mat-button-toggle [value]="option">{{
            answerLabel(option) | transloco: { n: option }
          }}</mat-button-toggle>
        }
      </mat-button-toggle-group>
      <div class="row">
        <mat-form-field subscriptSizing="dynamic" class="wide">
          <mat-label>{{ 'rob.assessment.justification' | transloco }}</mat-label>
          <input
            matInput
            [ngModel]="current()?.justification ?? ''"
            (change)="save({ justification: $any($event.target).value })"
            [disabled]="!editable()"
            maxlength="4000"
          />
        </mat-form-field>
        <mat-form-field subscriptSizing="dynamic" class="wide">
          <mat-label>{{ 'extraction.data.annotation' | transloco }}</mat-label>
          <mat-select
            [ngModel]="current()?.annotation_id ?? null"
            (ngModelChange)="save({ annotation_id: $event })"
            [disabled]="!editable()"
          >
            <mat-option [value]="null">{{ 'extraction.data.noAnnotation' | transloco }}</mat-option>
            @for (a of annotations(); track a.id) {
              <mat-option [value]="a.id"
                >{{ 'pdfs.page' | transloco: { page: a.page } }} · {{ a.quote }}</mat-option
              >
            }
          </mat-select>
        </mat-form-field>
        @if (passage(); as a) {
          <button mat-button type="button" (click)="showPassage.emit(a)">
            {{ 'rob.assessment.seePassage' | transloco }}
          </button>
        }
      </div>
    </div>
  `,
})
export class RobQuestion {
  readonly slot = input.required<AnswerSlot>();
  readonly options = input.required<string[]>();
  readonly label = input('');
  readonly current = input<AnswerOut | null>(null);
  readonly annotations = input<AnnotationOut[]>([]);
  readonly editable = input(false);
  readonly changed = output<AnswerIn>();
  readonly showPassage = output<AnnotationOut>();

  protected readonly passage = computed(() => {
    const id = this.current()?.annotation_id;
    return id ? (this.annotations().find((a) => a.id === id) ?? null) : null;
  });

  protected answerLabel(option: string): string {
    return /^\d+$/.test(option) ? 'rob.answer.stars' : 'rob.answer.' + option;
  }

  protected save(change: Partial<AnswerIn>): void {
    const now = this.current();
    this.changed.emit({
      question_key: this.slot().questionKey,
      outcome_id: this.slot().outcomeId,
      timepoint: this.slot().timepoint,
      answer: now?.answer ?? null,
      justification: now?.justification ?? null,
      annotation_id: now?.annotation_id ?? null,
      ...change,
    });
  }
}
