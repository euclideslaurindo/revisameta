# Implantação, backup e retenção

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

### 10.6 Implantação por fases (custo zero agora, expansão depois)

**Princípio:** o mesmo Docker Compose roda em qualquer lugar. Mudar de fase é copiar a configuração, restaurar o backup e apontar o endereço, sem reescrever código.

| Fase | Onde roda | Endereço | Quando |
|---|---|---|---|
| **F0 — Testes com usuários (atual)** | Computador do desenvolvedor | **Cloudflare Tunnel**: primeiro o túnel rápido (`trycloudflare.com`, sem conta), depois um túnel nomeado com domínio próprio | Sessões de teste agendadas com a Larissa e o grupo |
| **F1 — Beta contínuo** | **Oracle Cloud Always Free** (ARM, 2 OCPU / 12 GB) **ou** servidor/VM da UFAPE | Domínio próprio, HTTPS pelo Caddy, Cloudflare gratuito na frente | Quando houver uso fora das sessões agendadas |
| **F2 — Produção** | VPS paga ou serviços gerenciados | Domínio próprio | Só se houver verba e uso que justifique |

**Fase F0 — regras e limitações conhecidas**
- O sistema só fica no ar com o computador ligado; os testes são agendados.
- Túnel rápido: endereço muda a cada reinício, limite de 200 requisições simultâneas e **sem suporte a SSE** → por isso o fallback de polling é obrigatório (3.1). O túnel nomeado não tem essas limitações; usar assim que houver domínio.
- No túnel, a aplicação recebe o host do túnel: configurar hosts permitidos e CORS por variável de ambiente.
- Perfil `lite` disponível se o computador não aguentar a pilha completa (meta: rodar com 6 a 8 GB de RAM livres).
- Upload de PDFs grandes limitado pela velocidade de upload da internet do desenvolvedor.
- Backup diário para fora da máquina (10.8), porque perder o computador seria perder os dados de teste.

**Fase F1 — cuidados com o Oracle Always Free (para quando chegar a hora)**
- Pede cartão só para verificação; cartões brasileiros às vezes são recusados → plano B: servidor da UFAPE.
- A região principal não pode ser trocada depois; regiões concorridas podem dar "sem capacidade" (tentar de novo com script).
- Criar a máquina já dentro da cota gratuita desde o primeiro dia (máquinas acima da cota são desativadas ao fim do teste).
- Instâncias com uso muito baixo por muito tempo podem ser recuperadas pela Oracle: manter backup diário e o script `setup-servidor.sh` que recria o servidor do zero.
- Imagem Ubuntu da Oracle tem firewall próprio além das regras do painel: liberar 80/443 nos dois.
- O plano gratuito da Cloudflare limita cada requisição a 100 MB: o upload em partes (10.7) já resolve.
- Orçamento de memória aproximado: Postgres ~2 GB, Redis ~256 MB, FastAPI ~500 MB, worker ~1 GB, R ~1 GB por processo (2 processos), MinIO ~512 MB, Caddy e sistema ~1 GB.

**Comum a todas as fases**
- HTTPS sempre que exposto à internet (túnel ou Caddy).
- Migrations do Alembic rodam no deploy; nunca alterar o banco à mão.
- Deploy com verificação de `/health` e volta automática para a versão anterior se falhar (F1+).
- CI no GitHub Actions só com lint e testes (repositório privado tem minutos limitados); imagens construídas no próprio servidor na F1.
- Monitoramento gratuito e **fora** do servidor: UptimeRobot ou Healthchecks.io (disponibilidade e backup do dia) + Sentry no plano gratuito (erros).
- E-mail transacional gratuito (Brevo ou similar) com SPF/DKIM configurados quando houver domínio; na F0, convites podem ser copiados como link.
- Passo a passo completo em `docs/deploy.md`, incluindo como migrar de fase.

---

### 10.8 Backup, recuperação e retenção
- `pg_dump` diário + cópia incremental dos arquivos do MinIO, **criptografados** antes de sair da máquina.
- Destino gratuito **fora da hospedagem**: Google Drive do responsável via `rclone` (padrão) ou Backblaze B2.
- Retenção: 7 diários, 4 semanais, 3 mensais.
- Healthchecks.io avisa se o backup do dia não rodou.
- **Teste de restauração** documentado e executado antes de cada mudança de fase.
- Retenção de projetos: projetos sem acesso há muito tempo recebem aviso por e-mail e podem ser arquivados (prazo a definir, 17).
