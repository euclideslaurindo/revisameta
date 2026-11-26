import { Component, computed, inject, input } from '@angular/core';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { ProjectContext } from '../features/project/project-context';

/**
 * Says why a page is read-only for the current person (instead of silently greying
 * out buttons): which role can change it and which roles the person has.
 * Shown only when the person does not hold any of the `roles` allowed to edit.
 */
@Component({
  selector: 'rm-readonly-note',
  imports: [TranslocoPipe],
  template: `
    @if (show()) {
      <p class="notice readonly-note" role="note">
        {{ 'readonly.text' | transloco: { allowed: allowedText(), mine: mineText() } }}
      </p>
    }
  `,
})
export class ReadonlyNote {
  private readonly context = inject(ProjectContext);
  private readonly transloco = inject(TranslocoService);
  /** Roles that can edit this page. */
  readonly roles = input<string[]>(['admin']);

  private readonly mine = computed(() => this.context.project()?.my_roles ?? []);
  protected readonly show = computed(
    () => !!this.context.project() && !this.roles().some((r) => this.mine().includes(r as never)),
  );

  protected allowedText(): string {
    return this.roles()
      .map((r) => this.transloco.translate('roles.' + r))
      .join(this.transloco.translate('readonly.or'));
  }

  protected mineText(): string {
    return this.mine().length ? this.list(this.mine()) : this.transloco.translate('readonly.none');
  }

  private list(roles: readonly string[]): string {
    return roles.map((r) => this.transloco.translate('roles.' + r)).join(', ');
  }
}
