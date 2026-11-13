import { Component, input } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

import { asProblem } from '../core/errors/problem';

/** Shows a backend error (already translated) or a generic network message. */
@Component({
  selector: 'rm-form-error',
  imports: [TranslocoPipe],
  template: `
    @if (error()) {
      <div class="notice notice-error" role="alert">
        {{ message() ?? ('common.networkError' | transloco) }}
      </div>
    }
  `,
})
export class FormError {
  readonly error = input<unknown>(null);

  protected message(): string | null {
    return asProblem(this.error())?.title ?? null;
  }
}
