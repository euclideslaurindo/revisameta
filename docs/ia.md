# IA assistiva

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

### 7.15 IA assistiva (P1/P2, desligada por padrão)

> **Filosofia:** IA sozinha não é diferencial; quase todos os concorrentes já têm. O diferencial é **IA em que dá para confiar**: mostra a prova, é verificada automaticamente, é medida contra os humanos e ensina. Em revisão sistemática, uma IA que inventa um número é pior que nenhuma IA.

#### 7.15.1 Onde a IA entra (por ordem de prioridade e segurança)
| # | Função | O que faz | Prioridade |
|---|---|---|---|
| IA1 | **Tutor** | Chat que explica conceitos e **os resultados do próprio projeto** ("o que significa meu I² de 68%?"). Recebe os números já calculados pelo R e só explica. | P1 |
| IA2 | **Localizador de trechos** | "Onde o artigo fala de cegamento?", "onde está o DP do grupo controle?" → aponta página e trecho; a pessoa lê e decide. | P1 |
| IA3 | **Extração assistida** | Sugere valores **com citação exata**; lê legendas/rodapés e avisa "este valor parece ser EP, não DP" (reforça 7.5.1). | P2 |
| IA4 | **Segunda opinião em risco de viés** | Sugere respostas às perguntas sinalizadoras com o trecho que justifica. | P2 |
| IA5 | **Ajuda na estratégia de busca** | Sugere termos MeSH/DeCS e combinações para PubMed/LILACS; humano revisa e roda a busca. | P2 |
| IA6 | **Rascunho de Métodos/Resultados e do resumo** | Gera estrutura e texto; **os números são inseridos pelo sistema**, nunca escritos pela IA. | P2 |

A priorização de triagem (7.3) **não usa LLM**: é aprendizado de máquina clássico, local e gratuito.

#### 7.15.2 Onde a IA nunca entra
- Cálculos estatísticos (sempre o serviço R).
- Decisão final de inclusão/exclusão.
- Julgamento final de risco de viés.
- Qualquer número sem fonte verificada.

#### 7.15.3 Regras de segurança contra alucinação
1. **Citação verificada:** toda sugestão de IA2, IA3 e IA4 vem com a frase exata do PDF e a página. O backend confere se a frase existe no texto extraído do PDF (comparação normalizada, tolerando quebras de linha e hifenização). **Se não existir, a sugestão é descartada** e registrada como falha.
2. **Números do tutor e dos rascunhos:** a IA recebe os resultados como dados estruturados e escreve com marcadores (ex.: `{{pooled_effect}}`); o sistema substitui pelos valores reais. Se o texto da IA contiver um número que não veio dos dados, ele é sinalizado.
3. **Sugestão nunca é dado final:** campo fica "sugerido pela IA" até confirmação humana; o histórico registra a origem.
4. **Saída estruturada** (JSON com schema validado por Pydantic); resposta fora do schema é descartada.
5. **Contexto mínimo:** só os trechos/páginas necessários vão para o provedor, nunca o projeto inteiro.
6. **Prompt injection:** texto de PDF é tratado como dado, nunca como instrução; instruções do sistema separadas do conteúdo.

#### 7.15.4 Precisão medida (diferencial)
- Como há dupla avaliação humana, o sistema compara as sugestões da IA com o **consenso** dos revisores e mostra a taxa de acerto por tipo de tarefa e por projeto (ex.: "nas últimas 50 extrações, a IA acertou 46").
- Quando a precisão de uma função cair abaixo de um limiar configurável, ela é desativada para o projeto com aviso.
- Essas métricas entram na declaração de uso de IA exportável para o manuscrito.

#### 7.15.5 Provedores e custo zero
- **Camada de provedores** (interface única: `complete`, `complete_structured`, `embed`) com adaptadores trocáveis por configuração. Primeiro adaptador: **API gratuita do Gemini**. Previstos: DeepSeek, OpenAI-compatível genérico e **modelo local via Ollama** (para quem tiver máquina).
- **Aviso obrigatório de uso de dados:** no plano gratuito do Gemini, o Google pode usar prompts e respostas para melhorar os próprios produtos. Por isso:
  - a IA fica **desligada por padrão** em todo projeto;
  - para ligar, o admin do projeto lê e aceita um aviso claro (em pt e en) dizendo o que é enviado e para quem; o aceite fica na auditoria;
  - anotações privadas, comentários e dados ainda não publicados **nunca** são enviados; só trechos de artigos já publicados e resultados que o usuário pediu para explicar.
- **Limites do plano gratuito:** todas as chamadas passam pela fila, com controle de taxa global; ao atingir a cota, o sistema avisa e a função fica indisponível até renovar, sem quebrar o resto.
- **Cota de IA por usuário/dia** (6) para dividir o plano gratuito entre os usuários.
- **Cache** de respostas por (trecho, tarefa, versão do prompt) para não gastar cota duas vezes.
- Prompts versionados em arquivos (`backend/app/integrations/ai/prompts/`), com versão registrada em cada sugestão.
- Termos de uso de cada provedor revisados antes de ativar (alguns exigem 18+ ou restringem regiões).

#### 7.15.6 Interface
- Ícone e cor próprios para tudo que veio da IA; botão "ver trecho no PDF" em toda sugestão.
- Botões "aceitar", "corrigir" e "rejeitar" (os três alimentam a métrica 7.15.4).
- Tutor disponível em todas as telas pelo Modo Aprendizado, respondendo no idioma da interface.
- Exportar **declaração de uso de IA** para o manuscrito (funções usadas, provedor, versão do prompt, taxa de acerto, confirmação humana).
