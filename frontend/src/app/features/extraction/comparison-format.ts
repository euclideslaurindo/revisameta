import { ItemOut } from '../../core/api/models/item-out';
import { displayDecimal } from '../../shared/numbers';

type Translate = (key: string, params?: Record<string, unknown>) => string;

const ROW_LABELS: Record<string, string> = {
  present: 'consensus.field.rowPresent',
  value_type: 'extraction.data.valueType',
  dispersion_type: 'extraction.data.dispersionType',
  dispersion_source: 'extraction.data.dispersionSource',
  source_location: 'extraction.data.sourceLocation',
  mean: 'extraction.data.mean',
  events: 'extraction.data.events',
  total: 'extraction.data.total',
  t_stat: 'consensus.field.t_stat',
  p_value: 'consensus.field.p_value',
  adjusted: 'consensus.field.adjusted',
  adjusted_for: 'consensus.field.adjusted_for',
  effect_reported: 'consensus.field.effect_reported',
};
const MEASURE_LABELS: Record<string, string> = {
  scale_name: 'extraction.scale.name',
  scale_min: 'extraction.scale.min',
  scale_max: 'extraction.scale.max',
  higher_is_better: 'consensus.field.higherIsBetter',
};

/** Name of the compared field, in the interface language. */
export function fieldLabel(item: ItemOut, t: Translate): string {
  if (item.section === 'characteristics') {
    return item.label_key ? t(item.label_key) : (item.label ?? item.field);
  }
  if (item.field === 'n') return 'n';
  if (item.section === 'arm') return t('consensus.field.armPresent');
  if (item.section === 'measure') return t(MEASURE_LABELS[item.field] ?? item.field);
  if (ROW_LABELS[item.field]) return t(ROW_LABELS[item.field]);
  return t('extraction.data.fields.' + item.field);
}

/** Where the field is: characteristics, an arm, a scale or one outcome row. */
export function placeLabel(
  item: ItemOut,
  outcomeName: (id: string) => string,
  t: Translate,
): string {
  switch (item.section) {
    case 'characteristics':
      return t('consensus.section.characteristics');
    case 'arm':
      return t('consensus.section.arm', { arm: item.arm_label ?? '' });
    case 'measure':
      return t('consensus.section.scale', { outcome: outcomeName(item.outcome_id ?? '') });
    default:
      return t('consensus.section.row', {
        outcome: outcomeName(item.outcome_id ?? ''),
        timepoint: item.timepoint ?? '',
        arm: item.arm_label ?? '',
      });
  }
}

/** A compared value as the reader expects it (decimal comma in Portuguese, words for codes). */
export function formatValue(item: ItemOut, value: unknown, lang: string, t: Translate): string {
  if (value === null || value === undefined || value === '') return '—';
  if (item.field === 'present') {
    return t(value ? 'consensus.value.present' : 'consensus.value.absent');
  }
  if (typeof value === 'boolean') return t(value ? 'consensus.value.yes' : 'consensus.value.no');
  if (item.field === 'value_type') return t('extraction.data.' + value);
  if (item.field === 'dispersion_type') return t('extraction.dispersion.' + value);
  if (typeof value === 'object') {
    const e = value as Record<string, unknown>;
    const num = (v: unknown) =>
      v === null || v === undefined ? '' : displayDecimal(String(v), lang);
    const ci =
      e['ci_low'] != null || e['ci_high'] != null
        ? ` (${num(e['ci_low'])}–${num(e['ci_high'])})`
        : '';
    const se = e['se'] != null ? ` · ${t('extraction.data.fields.se')} ${num(e['se'])}` : '';
    return `${e['measure'] ?? ''} ${num(e['estimate'])}${ci}${se}`.trim();
  }
  if (item.kind === 'number') return displayDecimal(String(value), lang);
  return String(value);
}
