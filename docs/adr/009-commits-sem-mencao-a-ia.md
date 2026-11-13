# ADR-009: Commits sem menção a IA

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
Regra obrigatória do projeto: commits, PRs, comentários de código e changelog não mencionam IA nem assistentes.

## Decisão
Três camadas:
1. `.claude/settings.json` com `attribution.commit` e `attribution.pr` vazios (e `includeCoAuthoredBy: false` para versões antigas).
2. Hook `.githooks/commit-msg` que remove trailers `Co-Authored-By` de `@anthropic.com`, linhas `Claude-Session:`, rodapés "Generated with" e links de sessão, e faz o commit falhar se ainda sobrar alguma menção. Ativado com `git config core.hooksPath .githooks`.
3. Teste no CI que varre o histórico do branch e falha se encontrar essas menções.

O nome de arquivo `CLAUDE.md` pode aparecer em mensagens (é um arquivo do repositório); a verificação procura termos como "Claude Code", "anthropic" e "Generated with".

## Consequências
- Mensagens no padrão Conventional Commits, em inglês.
