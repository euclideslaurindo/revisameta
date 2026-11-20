# ADR-014: Forest plot com o semáforo do risco de viés ao lado

**Situação:** aceita (Etapa 4, 2026-11-19).

## Contexto
Pedido antigo e popular dos usuários do robvis (lição L18): ver o resultado de cada estudo e o risco de viés dele na mesma figura. O robvis fixado (`0c59cf1`) traz `rob_forest`, mas só para os modelos que ele tem (RoB 2, ROBINS-I 2016). O projeto usa também ROBINS-I V2, ROBINS-E, JBI, Newcastle-Ottawa e o genérico (ADR-013).

## Decisão
Usar `metafor::forest` e desenhar ao lado, como colunas próprias:
- os domínios (D1…Dn), ou as perguntas no JBI, NOS e genérico;
- o julgamento geral.

As colunas usam as mesmas cores e símbolos do semáforo do ADR-013, e a legenda traz o nome de cada nível em texto (10.3). Assim a figura funciona para todos os instrumentos e mantém um visual só.

## Consequências
- O gráfico é gerado pelo serviço R, como os outros.
- Um estudo sem avaliação final de risco de viés aparece com a coluna vazia e uma nota. Ele nunca é escondido.
- Se o robvis passar a cobrir todos os instrumentos, a troca fica isolada no serviço R.
