import { formatDate, registerLocaleData } from '@angular/common';
import localePt from '@angular/common/locales/pt';
import { Pipe, PipeTransform, inject } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';

registerLocaleData(localePt, 'pt-BR');

/**
 * Dates in the format of the interface language (14/11/2026 in Portuguese,
 * 11/14/2026 in English). Impure so it follows a language switch.
 */
@Pipe({ name: 'localDate', pure: false })
export class LocalDatePipe implements PipeTransform {
  private readonly transloco = inject(TranslocoService);

  transform(value: string | Date | null | undefined, format = 'mediumDate'): string {
    if (value === null || value === undefined || value === '') return '';
    const lang = this.transloco.getActiveLang() === 'en' ? 'en-US' : 'pt-BR';
    return formatDate(value, format, lang);
  }
}
