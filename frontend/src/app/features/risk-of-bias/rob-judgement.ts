import { Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { TranslocoPipe } from '@jsverse/transloco';

import { JudgementIn } from '../../core/api/models/judgement-in';

export interface JudgementView {
  suggested: string | null;
  final: string | null;
  justification: string | null;
  direction: string | null;
}

/**
 * The reviewer's judgement next to the system's suggestion. The suggestion never
 * becomes the judgement by itself; disagreeing needs a short justification.
 */
@Component({
  selector: 'rm-rob-judgement',
  imports: [FormsModule, TranslocoPipe, MatFormFieldModule, MatInputModule, MatSelectModule],
  template: `
    <div class="rob-judgement">
      @if (state().suggested; as s) {
        <p>
          {{ suggestedLabel() | transloco }}
          <span class="rob-level" [class]="'rob-level rob-level-' + s">{{ levelLabel()(s) }}</span>
        </p>
      } @else if (showNoSuggestion()) {
        <p class="muted">{{ 'rob.assessment.noSuggestion' | transloco }}</p>
      }
      <div class="row">
        <mat-form-field subscriptSizing="dynamic">
          <mat-label>{{ label() }}</mat-label>
          <mat-select
            [ngModel]="state().final"
            (ngModelChange)="save({ final: $event })"
            [disabled]="!editable()"
          >
            <mat-option [value]="null">—</mat-option>
            @for (level of levels(); track level) {
              <mat-option [value]="level">{{ levelLabel()(level) }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        @if (directions().length) {
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>{{ 'rob.assessment.direction' | transloco }}</mat-label>
            <mat-select
              [ngModel]="state().direction"
              (ngModelChange)="save({ direction: $event })"
              [disabled]="!editable()"
            >
              <mat-option [value]="null">—</mat-option>
              @for (d of directions(); track d) {
                <mat-option [value]="d">{{ 'rob.direction.' + d | transloco }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
        }
      </div>
      @if (disagrees() || state().justification) {
        <mat-form-field subscriptSizing="dynamic" class="wide block-field">
          <mat-label>
            {{
              (disagrees() ? 'rob.assessment.whyDisagree' : 'rob.assessment.justification')
                | transloco
            }}
          </mat-label>
          <input
            matInput
            [ngModel]="state().justification ?? ''"
            (change)="save({ justification: $any($event.target).value })"
            [disabled]="!editable()"
            maxlength="4000"
          />
        </mat-form-field>
      }
    </div>
  `,
})
export class RobJudgement {
  readonly domainKey = input<string | null>(null);
  readonly label = input('');
  readonly state = input.required<JudgementView>();
  readonly levels = input<string[]>([]);
  readonly directions = input<string[]>([]);
  readonly editable = input(false);
  readonly showNoSuggestion = input(false);
  /** Who suggests: the official algorithm, or the group's rule (JBI, NOS, generic). */
  readonly suggestedLabel = input('rob.assessment.suggested');
  /** Translated name of a level (group-defined levels are shown as typed). */
  readonly levelLabel = input<(level: string) => string>((l) => l);
  readonly changed = output<JudgementIn>();

  protected disagrees(): boolean {
    const s = this.state();
    return !!s.suggested && !!s.final && s.final !== s.suggested;
  }

  protected save(change: Partial<JudgementIn>): void {
    const s = this.state();
    this.changed.emit({
      domain_key: this.domainKey(),
      final: s.final,
      justification: s.justification,
      direction: s.direction,
      ...change,
    });
  }
}
