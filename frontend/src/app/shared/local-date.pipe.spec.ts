import { TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { describe, expect, it } from 'vitest';

import { LocalDatePipe } from './local-date.pipe';

function pipeFor(lang: string): LocalDatePipe {
  TestBed.configureTestingModule({
    providers: [{ provide: TranslocoService, useValue: { getActiveLang: () => lang } }],
  });
  return TestBed.runInInjectionContext(() => new LocalDatePipe());
}

describe('LocalDatePipe', () => {
  it('uses the day/month order of the interface language', () => {
    expect(pipeFor('pt-BR').transform('2026-11-14T13:05:00', 'dd/MM/yyyy')).toBe('14/11/2026');
    TestBed.resetTestingModule();
    expect(pipeFor('en').transform('2026-11-14T13:05:00', 'short')).toMatch(
      /^11\/14\/26, 1:05\sPM$/,
    );
    TestBed.resetTestingModule();
    expect(pipeFor('pt-BR').transform('2026-11-14T13:05:00', 'short')).toBe('14/11/2026 13:05');
  });

  it('shows nothing for an empty value', () => {
    expect(pipeFor('pt-BR').transform(null)).toBe('');
  });
});
