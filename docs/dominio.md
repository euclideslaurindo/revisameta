# Domínio, contexto e escopo

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

## 1. Contexto e objetivo

### 1.1 Problema
Uma estudante da área da saúde participa de uma revisão sistemática em grupo, para um resumo que será enviado a um congresso de neurocirurgia. Ela:
- foi colocada na etapa de **avaliação de risco de viés** e não tem experiência;
- considera a **estatística** (meta-análise) a parte mais difícil;
- usa ferramentas separadas, algumas pagas, e arquivos espalhados (Google Drive, um `.docx` de formulário por estudo, planilhas consolidadas).

Pergunta de pesquisa típica do grupo (formato de exemplo, sem dados reais):
> Pessoas com determinada condição que fizeram determinada cirurgia **antes dos 5 anos** tiveram melhor desfecho cognitivo do que as que fizeram **depois dos 5 anos**?

É uma comparação **entre dois grupos dentro de cada estudo** (precoce × tardio). Só entram na meta-análise principal os estudos que reportam os dois grupos. Os estudos provavelmente são **observacionais** (coortes), não ensaios randomizados.

### 1.2 Objetivo do sistema
Um lugar único, simples e guiado, que cubra o fluxo inteiro:

```
Protocolo → Importação → Deduplicação → Triagem → Texto completo → Extração
→ Risco de viés → Meta-análise → Certeza da evidência (GRADE) → PRISMA → Exportação/Resumo
```

O sistema também precisa **receber um projeto já em andamento** (lista final de estudos e avaliações já feitas em planilhas), porque é a situação real do grupo.

### 1.3 Princípios de produto
1. **Guiado:** cada etapa diz o que fazer, o que falta e qual o próximo passo.
2. **Dupla avaliação nativa:** dois revisores independentes + tela de conflitos nas etapas críticas.
3. **Rastreável:** toda decisão tem autor, data, justificativa e, se possível, trecho do PDF.
4. **Reprodutível:** toda análise pode ser exportada como **script R** que reproduz exatamente o resultado.
5. **Correto antes de bonito:** estatística validada contra o `metafor`.
6. **Gratuito e aberto:** sem dependências pagas obrigatórias.
7. **Prevenir erro humano:** o sistema desconfia dos números digitados, aponta o que parece errado e mostra a fonte no PDF ao lado. Este é o maior diferencial em relação às ferramentas existentes.
8. **Digitar uma vez, usar em tudo:** cada dado entra uma única vez e é reaproveitado em todas as análises, subgrupos e exportações.

---

## 2. Ferramentas de referência (o que estamos juntando)

| Ferramenta | O que pegamos dela | Módulo |
|---|---|---|
| **Rayyan** | Triagem rápida, destaque de palavras-chave, cegamento, motivos de exclusão | 7.3 |
| **Covidence** | Fluxo por etapas, conflitos, extração com formulário, contagens para PRISMA | 7.2 a 7.6 |
| **RevMan (Cochrane)** | Tabela "características dos estudos", forest plot, subgrupos | 7.7 |
| **robvis** | Gráficos semáforo (traffic light) e resumo de risco de viés | 7.6 |
| **RoB 2 / ROBINS-I / ROBINS-E (riskofbias.info)** | Domínios, perguntas sinalizadoras, algoritmos de julgamento | 7.6 |
| **JBI Critical Appraisal Tools** | Checklists por desenho (Sim/Não/Incerto/Não se aplica) | 7.6 |
| **Newcastle-Ottawa Scale (NOS)** | Avaliação de coortes e caso-controle por estrelas (muito usada em neurocirurgia) | 7.6 |
| **metafor / meta (R)** | Motor estatístico de referência | 8 |
| **JASP** | Interface de meta-análise "clicar e ver" | 7.7 |
| **Comprehensive Meta-Analysis (CMA)** | Entrada flexível de dados (médias, EP, IC, eventos, t, p) com conversão | 7.5 e 8.4 |
| **GRADEpro** | Tabela Summary of Findings e certeza da evidência | 7.8 |
| **PRISMA 2020 (fluxograma, checklist e PRISMA para resumos)** | Fluxograma automático e acompanhamento dos itens a relatar | 7.9 e 7.14 |
| **Zotero/Mendeley** | Exportação da bibliografia dos estudos incluídos | 7.10 |
| **WebPlotDigitizer** | (P2) Extrair valores de gráficos de artigos | 7.5 |

**Diferencial do RevisaMeta:** tudo integrado + **proteções contra erro de extração** + importação de projetos em andamento + Modo Aprendizado + script R exportável + gratuito.

### 2.1 Lições dos concorrentes (reclamações de usuários e estudos metodológicos)

Levantamento feito em fóruns, avaliações de usuários, issues do GitHub e artigos sobre as ferramentas. Cada problema virou um requisito.

| # | Problema encontrado | Onde | Requisito no RevisaMeta | Seção |
|---|---|---|---|---|
| L1 | Ferramentas fragmentadas: triagem/extração não fazem estatística; estatística não organiza a revisão | Covidence, Rayyan, RevMan | Fluxo completo em um lugar | 1.2 |
| L2 | Exportação da extração sai **em branco** se a etapa de consenso foi pulada | Covidence | Aviso antes de exportar + opção explícita de exportar extrações individuais | 7.10 |
| L3 | Modelo padrão de qualidade baseado em instrumento antigo (RoB 1) | Covidence | Instrumentos atuais com versão registrada | 7.6 |
| L4 | Deduplicação com muitos **falsos positivos** (compara só o começo do título; "Parte 1" e "Parte 2" viram duplicata) e duplicatas reais que passam | Rayyan | Deduplicação multicritério, explicada e sempre confirmada por humano | 7.2 |
| L5 | Lista de motivos de exclusão só cresce; não dá para apagar | Rayyan | Motivos editáveis (com histórico) | 7.4 |
| L6 | Sem **desfazer** a última decisão de triagem | Covidence (pedido de usuários) | Desfazer | 7.3 |
| L7 | Não dá para guardar referências excluídas mas úteis como contexto | Covidence (pedido de usuários) | Marcador "útil como referência" | 7.3 |
| L8 | Opções diferentes no celular e no computador (Sim/Não/Pular × Sim/Não/Talvez) | Covidence | Mesmas opções em qualquer tela | 7.3 e 10.3 |
| L9 | Não dá para dividir a triagem em lotes por coautor | Covidence (pedido de usuários) | Atribuição de lotes | 7.3 |
| L10 | Sem meta-regressão, sem rede, viés de publicação só visual; versão antiga presa ao estimador DerSimonian-Laird | RevMan | Motor metafor com estimador selecionável; Egger, leave-one-out, meta-regressão (P2) | 7.7 |
| L11 | Aceita só uma média e um DP: usuário com linha de base + final não sabe o que fazer | RevMan (fóruns) | Campos separados para valor final e mudança, com orientação | 7.5 |
| L12 | Subgrupos obrigam a **digitar os mesmos dados várias vezes**, gerando erros de cópia | RevMan | Digitar uma vez, reutilizar em todas as análises | 1.3 e 7.7 |
| L13 | Usuários travam ao inserir efeitos ajustados (HR/OR com IC) | RevMan (fóruns) | Entrada "efeito + IC" com conversão automática para log e EP | 7.5 e 8.5 |
| L14 | **Erros de extração são comuns e mudam conclusões**: em meta-análises com SMD, uma parte relevante não pôde ser replicada por n, média, DP ou sinal errados; a concordância entre extratores é baixa | Estudos metodológicos | Proteções anti-erro como prioridade máxima | 7.5.1 |
| L15 | **Confundir DP com EP** é um dos erros mais comuns e pode inflar muito o efeito | Estudos metodológicos | Tipo de dispersão obrigatório + detector de EP suspeito | 7.5.1 |
| L16 | robvis da versão CRAN quebra com "Sem informação" no ROBINS-I; rótulos sobrepostos | robvis (issues) | Versão fixada do GitHub + testes desses casos | 7.6 e 11.2 |
| L17 | robvis não tem template para JBI nem Newcastle-Ottawa (só o genérico) | robvis | Template genérico configurado ou gráfico próprio | 7.6 |
| L18 | Pedido antigo e popular: **forest plot com o semáforo de risco de viés ao lado** | robvis (issues) | Gráfico combinado | 7.7 |
| L19 | Custo: sem plano gratuito permanente | Covidence, CMA | Gratuito | 1.3 |

Regra para o Claude Code: ao implementar um módulo, consulte esta tabela e garanta que os requisitos ligados a ele estão cobertos.

---

## 5. Glossário de domínio (usar na interface e no Modo Aprendizado)

| Termo | Explicação simples |
|---|---|
| Revisão sistemática | Estudo que reúne todos os estudos sobre uma pergunta, seguindo um método fixo e transparente |
| Meta-análise | Parte estatística que combina os números de vários estudos em um resultado único |
| PICO / PECO | População, Intervenção (ou Exposição), Comparação, Outcome (desfecho) |
| Protocolo / PROSPERO | Plano registrado antes de começar, para evitar mudar regras no meio |
| Emenda ao protocolo | Mudança no plano depois de começar; precisa ser registrada e justificada |
| Triagem | Ler título/resumo e decidir se o estudo pode servir |
| Texto completo | Segunda triagem, lendo o artigo inteiro |
| Estudo × relato | Um mesmo estudo (mesmos pacientes) pode ter vários artigos publicados |
| Extração de dados | Copiar do artigo os números necessários (n, média, DP, eventos...) |
| Risco de viés | Avaliar se o jeito como o estudo foi feito pode ter distorcido o resultado |
| Domínio (RoB) | Uma área avaliada (ex.: confundimento, dados faltantes) |
| Pergunta sinalizadora | Pergunta que ajuda a julgar um domínio |
| Confundimento | Outro fator que influencia tanto o grupo quanto o desfecho e distorce a comparação |
| Estimativa ajustada | Resultado corrigido para fatores de confusão (comum em estudos observacionais) |
| Medida de efeito | Número que resume a diferença entre grupos (MD, SMD, OR, RR) |
| SMD / g de Hedges | Diferença de médias padronizada; usada quando estudos medem com escalas diferentes |
| IC 95% | Faixa onde o valor verdadeiro provavelmente está |
| Efeito fixo | Supõe que todos os estudos medem o mesmo efeito verdadeiro |
| Efeitos aleatórios | Supõe que o efeito verdadeiro varia entre estudos (mais comum na prática) |
| Heterogeneidade | Quanto os resultados dos estudos diferem entre si |
| I² | % da variação entre estudos que não é explicada pelo acaso |
| τ² (tau²) | Variância do efeito verdadeiro entre estudos |
| Intervalo de predição | Faixa onde provavelmente cairia o efeito de um novo estudo |
| Forest plot | Gráfico com o resultado de cada estudo e o combinado (losango) |
| Funnel plot | Gráfico para investigar viés de publicação |
| Sensibilidade | Refazer a análise mudando algo para ver se o resultado se mantém |
| Subgrupo | Analisar separado por característica (ex.: tipo de cirurgia) |
| Meta-regressão | Ver se uma característica numérica dos estudos (ex.: idade média) explica a diferença nos resultados |
| Unidade de análise | Garantir que os mesmos pacientes não sejam contados duas vezes |
| GRADE | Classifica a certeza da evidência (alta, moderada, baixa, muito baixa) |
| PRISMA | Diretriz de como relatar a revisão; inclui fluxograma e checklist |

---

## 6. Usuários, papéis e acesso

| Papel | Pode |
|---|---|
| **Administrador do projeto** | Criar projeto, convidar membros, configurar protocolo, formulários e instrumentos, resolver conflitos, travar etapas, registrar emendas |
| **Revisor** | Triar e avaliar risco de viés; com cegamento ativo, vê só as próprias decisões |
| **Extrator** | Extrair dados nos formulários |
| **Estatístico** | Configurar e rodar análises, exportar resultados |
| **Leitor** | Ver tudo, sem editar (ex.: orientador) |

Regras:
- Um usuário pode ter vários papéis no mesmo projeto e participar de vários projetos.
- **Convites** por link com expiração (e-mail opcional no MVP: o admin pode copiar o link).
- **Recuperação de senha** por e-mail (P1; no MVP, o admin do sistema redefine).
- **Cegamento:** enquanto ativo, um revisor não vê as decisões do outro naquela etapa, nem pela API. O admin revela quando os dois terminaram.
- Toda ação de escrita gera registro na **auditoria**.
- O criador do projeto não pode ser removido sem transferir a administração.

**Sistema aberto ao público (cadastro livre):**
- Cadastro com **verificação de e-mail** e **captcha gratuito** (Cloudflare Turnstile).
- **Cotas por usuário e por projeto** configuráveis pelo administrador do sistema (ex.: número de projetos, espaço de PDFs, uso de IA por dia), com painel de uso. Sem cotas, um único usuário pode lotar o servidor gratuito.
- Papel global **administrador do sistema** (diferente do admin de projeto): gerencia cotas, usuários, denúncias e status; **não** acessa o conteúdo dos projetos sem ser membro.
- Aviso permanente de **"versão beta, sem garantia de disponibilidade"** enquanto estiver na infraestrutura gratuita.
- Canal de contato para pedidos de remoção (direitos autorais, LGPD).

---

## 16. Fora do escopo (por enquanto)
- Meta-análise em rede (network meta-analysis).
- Meta-análise de acurácia diagnóstica (QUADAS-2, curvas SROC).
- Meta-análise de dados individuais de pacientes (IPD).
- Busca automática direta nas bases (PubMed API) — avaliar depois do MVP.
- Aplicativo mobile nativo.
- Planos pagos, cobrança e assinatura (só depois da fase F2, se fizer sentido).
- Idiomas além de português e inglês.

---

## 17. Perguntas em aberto (confirmar com o grupo antes das etapas indicadas)
1. Quem do grupo vai usar o sistema e com quais papéis? *(Etapa 0)*
2. Qual a data limite de submissão do resumo? *(define a ordem das Etapas 2 e 3)*
3. Quais instrumentos de risco de viés o grupo usa de fato (JBI, ROBINS-I, NOS)? Qual versão? Qual a regra de classificação no JBI/NOS? *(Etapa 2)*
4. O grupo tem permissão para usar o texto completo dos checklists dentro do sistema? *(Etapa 2)*
5. Em que formato estão hoje as avaliações e a tabela consolidada (colunas, valores usados)? *(Etapa 2, migração)*
6. Qual o desfecho cognitivo principal, quais escalas e em quais momentos? *(Etapa 3)*
7. Os estudos usam o mesmo corte de 5 anos? Se não, qual regra adotar? *(Etapa 3)*
8. Usar estimativas ajustadas ou não ajustadas? *(Etapa 3)*
9. A dupla extração dos dados numéricos será obrigatória? Quem confere? *(Etapa 1)*
10. A UFAPE tem servidor ou VM disponível para a fase F1? *(antes da F1)*
11. O cadastro no Oracle Always Free é aceito com o cartão disponível? Qual região? *(antes da F1)*
12. Domínio: o gratuito do Student Pack (1º ano) ou subdomínio gratuito? *(fim da Etapa 0)*
13. Prazo de retenção de projetos inativos? *(Etapa 6)*
14. Licença do código antes de um dia tornar o repositório público (ex.: AGPL × MIT)? *(antes de abrir o repositório)*

Decisões já tomadas (não perguntar de novo): custo zero; hospedagem por fases começando no computador do desenvolvedor com Cloudflare Tunnel; repositório privado; sistema aberto ao público com cadastro; interface e saídas em português e inglês; sem prazo, todas as funcionalidades na ordem das etapas; commits sem menção a IA; IA desligada por padrão e com Gemini gratuito como primeiro provedor.

---

## 18. Referências para consulta (verificar a versão atual)
- Cochrane Handbook for Systematic Reviews of Interventions (capítulos de extração, risco de viés, meta-análise e estudos não randomizados)
- PRISMA 2020 Statement, fluxograma, checklist e PRISMA for Abstracts
- RoB 2, ROBINS-I e ROBINS-E — riskofbias.info
- JBI Critical Appraisal Tools — jbi.global
- Newcastle-Ottawa Scale — Ottawa Hospital Research Institute
- Documentação do `metafor` (Viechtbauer), do `meta` (Schwarzer) e do `robvis` (McGuinness & Higgins)
- GRADE Handbook
- Wan et al. (2014) e Luo et al. (2018), para estimar média e DP a partir de mediana
- Gøtzsche et al. (2007), "Data extraction errors in meta-analyses that use standardized mean differences" (JAMA)
- Tendal et al. (2009), variação entre observadores ao extrair dados para SMD (BMJ)
- Kanellopoulou et al., erros estatísticos comuns em meta-análises (Cochrane Evidence Synthesis and Methods)
- Estudo sobre a confusão EP/DP em meta-análises de medicina esportiva (Sports Medicine) e o levantamento de erros comuns de Kadlec et al.
- Issues do repositório `mcguinlu/robvis` no GitHub (bugs conhecidos)
- Documentação do Cloudflare Tunnel (túnel rápido e nomeado, limitações)
- Documentação do Oracle Cloud Always Free (cotas atuais e política de instâncias ociosas)
- Preços e termos da API do Gemini (plano gratuito e uso de dados)
- Documentação do Claude Code sobre a configuração `attribution`
- ASReview (priorização de triagem com aprendizado ativo)
- Documentação do FastAPI, SQLAlchemy 2.0, Alembic e Angular
