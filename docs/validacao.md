# Validação e testes

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

## 11. Validação e testes (critério de "pronto")

### 11.1 Testes de referência estatística (obrigatórios)
1. Em `stats-r/fixtures/`, um script roda o `metafor` com datasets públicos (`dat.bcg` para dicotômico e pelo menos um dataset contínuo do próprio pacote) e salva os resultados esperados em JSON: estimativa, EP, IC, τ², I², Q, intervalo de predição, para REML, DL, efeito fixo e com/sem Hartung-Knapp.
2. Testes `testthat` comparam a saída de cada endpoint com as fixtures (tolerância de 1e-6).
3. Teste de integração no Python: mesmos dados pela API → mesmo resultado da fixture.
4. Teste E2E: mesmos dados pela interface → mesmo resultado na tela.
5. O script R exportado, rodado em um R limpo, reproduz os mesmos números.
6. Conferência cruzada opcional com uma segunda implementação (ex.: `meta` ou `PyMARE`) para pegar erros de configuração.

### 11.2 Testes de domínio
- Algoritmos de julgamento RoB 2/ROBINS-I: tabela de casos (combinações de domínios → julgamento geral esperado).
- Regras configuráveis de JBI/NOS.
- Inversão de direção da escala.
- Conversões (8.5) e combinação de braços: casos com valores calculados no R.
- Bloqueios: estudo duplicado na análise; SMD com mistura de final e mudança; k < 2.
- Cegamento: revisor A não lê decisões do revisor B via API enquanto ativo.
- Isolamento: usuário de um projeto não acessa dados de outro (todo endpoint).
- Trava otimista: edição simultânea gera conflito, não sobrescrita.
- Importação/migração: arquivos com colunas faltando, vírgula decimal, linhas inválidas.
- **Proteções anti-erro (7.5.1)** com casos sintéticos: EP digitado como DP (deve gerar alerta); p reportado incompatível com média/DP/n (alerta); sinal invertido em escala "maior é pior"; soma dos braços maior que o total (bloqueio); dupla extração com diferença numérica real (divergência) e só de formatação (sem divergência); correção de um dado marca análises como desatualizadas.
- **Deduplicação:** "Parte 1" × "Parte 2", errata × artigo original e títulos que diferem só no fim **não** viram duplicata; mesmo DOI sempre vira.
- **robvis:** ROBINS-I com "Sem informação" e "Grave" no mesmo gráfico renderiza as duas categorias corretamente; muitos estudos e nomes longos sem sobreposição de rótulos.
- **Exportação sem consenso:** gera aviso e nunca arquivo em branco.
- **Triagem:** desfazer restaura a decisão anterior e registra na auditoria.
- **IA:** citação inexistente no PDF é descartada; número no texto da IA que não veio dos dados é sinalizado; resposta fora do schema é descartada; projeto com IA desligada nunca chama o provedor; cota esgotada não quebra o sistema; provedor falso (mock) usado em todos os testes, sem chamadas reais no CI.
- **Arquivos grandes:** upload retomado após queda; PDF duplicado ocupa espaço uma vez; arquivo com extensão .pdf mas outro tipo real é rejeitado; exportação grande não estoura a memória do backend.
- **i18n:** nenhuma chave faltando em pt-BR ou en (teste automático); gráficos gerados nos dois idiomas.
- **Cotas:** usuário que excede a cota recebe mensagem clara e não derruba o sistema.
- **Fallback de progresso:** com SSE indisponível, a tela de progresso funciona por polling.

### 11.3 Gerais
- Cobertura mínima de 80% no backend e no serviço R.
- E2E (Playwright) do fluxo mínimo: criar projeto → cadastrar 4 estudos → extrair → avaliar risco de viés com 2 revisores → resolver conflito → rodar meta-análise → exportar forest plot, gráficos de RoB e script R.
- E2E da migração: importar tabela consolidada de RoB existente → gráficos iguais aos do robvis web.
- CI (GitHub Actions) roda lint, tipos e todos os testes em cada push.
