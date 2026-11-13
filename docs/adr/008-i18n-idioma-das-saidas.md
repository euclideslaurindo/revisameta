# ADR-008: i18n pt-BR/en com idioma das saídas separado do idioma da interface

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
Usuários brasileiros usam a interface em português, mas costumam submeter a congressos e revistas em inglês.

## Decisão
- Frontend com **Transloco**; nenhum texto fixo em componentes. Um teste automático falha se faltar chave em `pt-BR` ou `en`.
- Mensagens de erro e e-mails do backend também nos dois idiomas.
- O **idioma das saídas** (gráficos, tabelas, PRISMA, SoF) é escolhido em cada exportação, independente do idioma da interface; o serviço R recebe o idioma como parâmetro.
- Formato de número segue o idioma das saídas; armazenamento sempre numérico.

## Consequências
- Todo texto novo nasce com as duas traduções.
