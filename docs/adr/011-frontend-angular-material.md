# ADR-011: Frontend em Angular 22 + Angular Material (no lugar do PrimeNG)

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
A especificação previa o PrimeNG. A partir da versão 22 (nov/2026), o PrimeNG deixou de ser MIT e passou à licença comercial "PrimeUI": a versão Community gratuita exige uma chave renovada todo ano, proíbe redistribuir o código e mostra um selo "Invalid PrimeUI License" sem a chave. O PrimeNG 21 continua MIT, mas exige o Angular 21.

## Decisão
- Angular 22 (versão estável mais recente) com **Angular Material/CDK** (MIT, mantido pelo time do Angular).
- Tabelas grandes (triagem, extração) serão montadas com `mat-table` + CDK (rolagem virtual, ordenação, filtros).
- Testes unitários com **Vitest**, o padrão do Angular 22 (a especificação citava Jest ou Karma).
- Sem fontes ou ícones do Google Fonts: nenhuma requisição a terceiros (LGPD, CSP).
- O build de produção desliga o "inline de CSS crítico", que depende de um `onload` embutido bloqueado pela nossa CSP.

## Consequências
- Sem chave de licença nem risco de mudança de licença na biblioteca de componentes.
- Mais trabalho para montar tabelas avançadas do que com o PrimeNG.
