# ADR-007: IA desligada por padrão, provedores trocáveis, citação verificada e precisão medida

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
Em revisão sistemática, uma IA que inventa um número é pior que nenhuma IA. O plano gratuito do Gemini permite ao Google usar os dados enviados.

## Decisão
- IA **desligada por padrão** em todo projeto; ligar exige aceitar um aviso de uso de dados, registrado na auditoria.
- Camada de provedores com interface única (`complete`, `complete_structured`, `embed`); primeiro adaptador: Gemini gratuito. Mock em todos os testes.
- Toda sugestão com citação é conferida contra o texto do PDF; sem correspondência, é descartada. Números em textos vêm de marcadores preenchidos pelo sistema.
- A IA nunca calcula estatística, nunca decide inclusão e nunca dá o julgamento final de risco de viés.
- Precisão medida contra o consenso humano; abaixo do limiar, a função é desligada para o projeto.

## Consequências
- Implementação na Etapa 7; até lá, nenhum código de IA.
- Cotas por usuário/dia e cache para caber no plano gratuito.
