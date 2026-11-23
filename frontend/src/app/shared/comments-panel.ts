import { DatePipe } from '@angular/common';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { TranslocoPipe } from '@jsverse/transloco';

import { Api } from '../core/api/api';
import { AuthService } from '../core/auth/auth';
import { createComment } from '../core/api/fn/comments/create-comment';
import { deleteComment } from '../core/api/fn/comments/delete-comment';
import { editComment } from '../core/api/fn/comments/edit-comment';
import { listComments } from '../core/api/fn/comments/list-comments';
import { mentionableMembers } from '../core/api/fn/comments/mentionable-members';
import { CommentOut } from '../core/api/models/comment-out';
import { MentionOut } from '../core/api/models/mention-out';
import { withJsonBody } from '../core/errors/problem';
import { ProjectContext } from '../features/project/project-context';
import { FormError } from './form-error';

/** Comments on a study, reference or analysis, with mentions of project members. */
@Component({
  selector: 'rm-comments-panel',
  imports: [
    DatePipe,
    FormsModule,
    TranslocoPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    FormError,
  ],
  template: `
    <rm-form-error [error]="error()" />
    @for (c of comments(); track c.id) {
      <div class="comment">
        <div class="muted">
          <strong>{{ c.author_name }}</strong> · {{ c.created_at | date: 'short' }}
          @if (c.edited) {
            · {{ 'comments.edited' | transloco }}
          }
          @if (c.field) {
            · {{ 'comments.field' | transloco }}: {{ c.field }}
          }
        </div>
        @if (editing() === c.id) {
          <mat-form-field subscriptSizing="dynamic" class="full">
            <textarea matInput rows="2" maxlength="4000" [(ngModel)]="editText"></textarea>
          </mat-form-field>
          <button mat-button type="button" [disabled]="busy()" (click)="saveEdit(c)">
            {{ 'comments.save' | transloco }}
          </button>
          <button mat-button type="button" (click)="editing.set(null)">
            {{ 'comments.cancel' | transloco }}
          </button>
        } @else {
          <p class="text">{{ c.text }}</p>
          @if (c.mentions.length) {
            <div class="muted">
              {{ 'comments.mentions' | transloco }}:
              @for (m of c.mentions; track m.user_id; let last = $last) {
                @{{ m.name }}{{ last ? '' : ', ' }}
              }
            </div>
          }
          @if (c.author_id === me()) {
            <button mat-button type="button" (click)="startEdit(c)">
              {{ 'comments.edit' | transloco }}
            </button>
          }
          @if (c.author_id === me() || isAdmin()) {
            <button mat-button type="button" [disabled]="busy()" (click)="remove(c)">
              {{ 'comments.remove' | transloco }}
            </button>
          }
        }
      </div>
    } @empty {
      <p class="muted">{{ 'comments.empty' | transloco }}</p>
    }
    <mat-form-field subscriptSizing="dynamic" class="full">
      <mat-label>{{ 'comments.new' | transloco }}</mat-label>
      <textarea matInput rows="2" maxlength="4000" [(ngModel)]="text"></textarea>
    </mat-form-field>
    <div class="row">
      <mat-form-field subscriptSizing="dynamic" class="wide">
        <mat-label>{{ 'comments.mention' | transloco }}</mat-label>
        <mat-select multiple [(ngModel)]="mentions">
          @for (m of members(); track m.user_id) {
            <mat-option [value]="m.user_id">{{ m.name }}</mat-option>
          }
        </mat-select>
      </mat-form-field>
      <mat-form-field subscriptSizing="dynamic">
        <mat-label>{{ 'comments.field' | transloco }}</mat-label>
        <input matInput maxlength="120" [(ngModel)]="field" />
      </mat-form-field>
      <button mat-flat-button type="button" [disabled]="busy() || !text.trim()" (click)="add()">
        {{ 'comments.send' | transloco }}
      </button>
    </div>
  `,
  styles: `
    .comment {
      border-left: 3px solid var(--mat-sys-outline-variant);
      padding-left: 8px;
      margin-bottom: 12px;
    }
    .text {
      white-space: pre-wrap;
      margin: 4px 0;
    }
    .full {
      width: 100%;
    }
  `,
})
export class CommentsPanel {
  private readonly api = inject(Api);
  private readonly auth = inject(AuthService);
  private readonly context = inject(ProjectContext);

  readonly entity = input.required<'study' | 'reference' | 'analysis'>();
  readonly entityId = input.required<string>();

  protected readonly comments = signal<CommentOut[]>([]);
  protected readonly members = signal<MentionOut[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<unknown>(null);
  protected readonly editing = signal<string | null>(null);
  protected readonly me = computed(() => this.auth.user()?.id ?? null);
  protected readonly isAdmin = computed(
    () => this.context.project()?.my_roles?.includes('admin') ?? false,
  );

  protected text = '';
  protected field = '';
  protected mentions: string[] = [];
  protected editText = '';

  constructor() {
    effect(() => void this.load(this.entityId()));
  }

  private projectId(): string {
    return this.context.project()!.id;
  }

  private async load(entityId: string): Promise<void> {
    await this.guard(async () => {
      const project_id = this.projectId();
      const [comments, members] = await Promise.all([
        this.api.invoke(listComments, { project_id, entity: this.entity(), entity_id: entityId }),
        this.api.invoke(mentionableMembers, { project_id }),
      ]);
      this.comments.set(comments);
      this.members.set(members);
    });
  }

  async add(): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(createComment, {
        project_id: this.projectId(),
        body: {
          entity: this.entity(),
          entity_id: this.entityId(),
          text: this.text,
          field: this.field.trim() || null,
          mentions: this.mentions,
        },
      });
      this.text = '';
      this.field = '';
      this.mentions = [];
    });
    await this.load(this.entityId());
  }

  protected startEdit(c: CommentOut): void {
    this.editText = c.text;
    this.editing.set(c.id);
  }

  async saveEdit(c: CommentOut): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(editComment, {
        project_id: this.projectId(),
        comment_id: c.id,
        body: {
          text: this.editText,
          mentions: c.mentions.map((m) => m.user_id),
          version: c.version,
        },
      });
      this.editing.set(null);
    });
    await this.load(this.entityId());
  }

  async remove(c: CommentOut): Promise<void> {
    await this.guard(async () => {
      await this.api.invoke(deleteComment, { project_id: this.projectId(), comment_id: c.id });
    });
    await this.load(this.entityId());
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
