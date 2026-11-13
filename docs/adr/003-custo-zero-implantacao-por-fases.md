# ADR-003: Custo zero e implantação por fases

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
Não há orçamento. O sistema precisa ser testado com usuários reais sem gastar nada e poder crescer depois sem reescrita.

## Decisão
O mesmo Docker Compose roda em todas as fases:
- **F0 (atual):** computador do desenvolvedor, exposto pelo Cloudflare Tunnel (primeiro o túnel rápido, depois um túnel nomeado com domínio).
- **F1:** Oracle Cloud Always Free (ARM) ou servidor da UFAPE, com domínio e HTTPS pelo Caddy.
- **F2:** VPS paga, só se houver verba e uso.

Todas as imagens com suporte amd64 e arm64. Nenhum serviço pago ou que exija cartão entra sem aprovação explícita.

**Rejeitado:** Vercel + Supabase como plataforma principal (o serviço R e a fila não rodam em serverless; o Supabase gratuito tem 500 MB de banco, 1 GB de arquivos, pausa após 7 dias sem uso e não tem backup diário).

## Consequências
- Mudar de fase = copiar configuração, restaurar backup e apontar o endereço.
- Na F0 o sistema só fica no ar com o computador ligado; testes são agendados e há backup diário fora da máquina.
- O túnel rápido não suporta SSE, por isso o fallback de polling é obrigatório (ADR-005).
