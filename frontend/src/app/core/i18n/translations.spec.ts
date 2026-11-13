import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

interface Tree {
  [key: string]: string | Tree;
}

function load(lang: string): Tree {
  return JSON.parse(readFileSync(join('public', 'i18n', `${lang}.json`), 'utf-8')) as Tree;
}

function keys(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === 'string' ? [`${prefix}${key}`] : keys(value, `${prefix}${key}.`),
  );
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === 'api' ? [] : sourceFiles(path);
    return path.endsWith('.ts') && !path.endsWith('.spec.ts') ? [path] : [];
  });
}

describe('translations (ADR-008)', () => {
  const pt = keys(load('pt-BR')).sort();
  const en = keys(load('en')).sort();

  it('pt-BR and en define exactly the same keys', () => {
    expect(en).toEqual(pt);
  });

  it('no translation is empty', () => {
    const flat = (tree: Tree): string[] =>
      Object.values(tree).flatMap((v) => (typeof v === 'string' ? [v] : flat(v)));
    expect(flat(load('pt-BR')).every((v) => v.trim().length > 0)).toBe(true);
    expect(flat(load('en')).every((v) => v.trim().length > 0)).toBe(true);
  });

  it('every static key used in templates exists', () => {
    const used = new Set<string>();
    for (const file of sourceFiles(join('src', 'app'))) {
      const text = readFileSync(file, 'utf-8');
      for (const match of text.matchAll(/'([a-zA-Z]+\.[a-zA-Z.]+)'\s*\|\s*transloco/g)) {
        used.add(match[1]);
      }
    }
    const missing = [...used].filter((key) => !pt.includes(key));
    expect(missing).toEqual([]);
    expect(used.size).toBeGreaterThan(10);
  });
});
