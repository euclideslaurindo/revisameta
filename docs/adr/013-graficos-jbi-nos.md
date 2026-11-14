# ADR-013: Gráficos de risco de viés para JBI, Newcastle-Ottawa e ROBINS-I V2

**Situação:** proposta (Etapa 2), aguardando aprovação.

## Contexto
O robvis fixado no commit `0c59cf1` tem templates para ROB2, ROB2-Cluster, ROBINS-I (versão 2016), ROBINS-E, QUADAS-2, QUIPS e Generic. Não há template para JBI nem Newcastle-Ottawa (lição L17), nem para a versão 2 do ROBINS-I (rascunho revisado de nov 2025). A especificação (7.6) pede decidir entre o template genérico com domínios configurados ou um gráfico próprio em `ggplot2` com o mesmo visual.

## Decisão proposta
1. **Usar o template `Generic` do robvis** sempre que ele aceitar os rótulos do instrumento:
   - ROBINS-I V2: domínios D1–D6 e as categorias de julgamento da V2.
   - JBI: cada pergunta do checklist vira uma coluna; as respostas (Sim, Não, Incerto, Não se aplica) viram os rótulos do semáforo; a coluna "Geral" mostra o julgamento do grupo (sem nota total).
   - Newcastle-Ottawa: colunas por bloco (seleção, comparabilidade, desfecho/exposição) com as estrelas atribuídas; "Geral" segue as faixas que o grupo definiu.
2. **Gráfico próprio em `ggplot2`, com o mesmo visual do robvis, só se o `Generic` não aceitar** os rótulos ou as cores necessários. Essa verificação é o primeiro teste do passo de gráficos; o resultado atualiza este ADR.
3. Em todos os casos, cores sempre acompanhadas de rótulo em texto (10.3) e testes de rótulos longos e muitos estudos.

## Consequências
- Um único serviço de gráficos (R) e um único visual para todos os instrumentos.
- Se o robvis ganhar templates oficiais para esses instrumentos, a troca fica isolada no serviço R.
