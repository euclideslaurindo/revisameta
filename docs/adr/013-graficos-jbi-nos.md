# ADR-013: Gráficos de risco de viés para JBI, Newcastle-Ottawa e ROBINS-I V2

**Situação:** aceita (Etapa 2, passo 4), com o resultado do teste previsto no item 2.

## Contexto
O robvis fixado no commit `0c59cf1` tem templates para ROB2, ROB2-Cluster, ROBINS-I (versão 2016), ROBINS-E, QUADAS-2, QUIPS e Generic. Não há template para JBI nem Newcastle-Ottawa (lição L17), nem para a versão 2 do ROBINS-I (rascunho revisado de nov 2025). A especificação (7.6) pede decidir entre o template genérico com domínios configurados ou um gráfico próprio em `ggplot2` com o mesmo visual.

## O que o teste mostrou (`Generic` do robvis)
- O `Generic` aceita qualquer número de colunas e rótulos traduzidos, mas tem **seis categorias fixas** (baixo, algumas preocupações, alto, crítico, sem informação, não se aplica), cada uma com uma cor e um rótulo na legenda.
- Ele **classifica pela primeira letra** de cada palavra. Um "Não"/"No" vira "sem informação", e letras soltas somem. Por isso o serviço R nunca manda o texto que as pessoas leem: manda palavras em inglês que caem exatamente na categoria certa, e os rótulos traduzidos só aparecem na legenda.
- **ROBINS-I V2 e ROBINS-E** têm o nível "baixo, exceto pelo confundimento não controlado", que não tem categoria no robvis.
- **JBI, Newcastle-Ottawa e o instrumento genérico** não têm julgamento por domínio. As colunas são respostas (Sim/Não/Incerto, estrelas), e o julgamento geral usa outra escala (a regra do grupo). Com seis categorias e um rótulo por cor, a legenda ficaria errada.

## Decisão
1. **robvis `Generic`** quando cada nível do instrumento cabe numa categoria própria do robvis: **RoB 2 e ROBINS-I 2016**. Assim os gráficos ficam iguais aos do robvis web.
2. **Gráfico próprio em `ggplot2`, com o mesmo visual** (cores Cochrane do robvis, símbolos + − x ! ?, legenda com texto) para **ROBINS-I V2, ROBINS-E, JBI, Newcastle-Ottawa e genérico**:
   - "Baixo, exceto confundimento" ganha um verde mais claro, com o próprio rótulo.
   - JBI e genérico: uma coluna por pergunta (Q1…Qn, com legenda das perguntas abaixo do gráfico) e a coluna "Geral" com o julgamento do grupo. **Nunca há nota total.**
   - Newcastle-Ottawa: uma coluna por item, com o número de estrelas no círculo. A cor é verde no máximo do item, vermelha em zero e amarela no meio (só no item de comparabilidade, que vale até 2).
3. A escolha é automática no serviço R (`R/rob_plots.R`), pela lista de níveis. O backend manda sempre a mesma tabela normalizada.
4. Em todos os casos: cores sempre com rótulo em texto (10.3); idioma do gráfico escolhido na hora, separado do idioma da tela (ADR-008); SVG ou PNG a 300 dpi; o tamanho cresce com o número de estudos e nomes longos quebram em linhas.

## Consequências
- Um único serviço de gráficos (R) e um único visual para todos os instrumentos.
- Testes em `stats-r/tests/testthat/test-rob-plots.R`: as duas engines; "Sem informação" e "Grave" juntos no ROBINS-I; um rótulo "No" que não vira "sem informação"; 40 estudos com nomes longos; PNG válido.
- Se o robvis ganhar templates oficiais para esses instrumentos, a troca fica isolada em `R/rob_plots.R`.
