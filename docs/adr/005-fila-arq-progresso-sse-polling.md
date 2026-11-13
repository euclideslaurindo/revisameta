# ADR-005: Fila arq + Redis; progresso por SSE com fallback de polling

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
Processamento de PDF, importações grandes, ZIPs, gráficos e chamadas de IA não cabem no tempo de uma requisição. O túnel rápido da Cloudflare não suporta SSE.

## Decisão
Redis + `arq` (assíncrono, como o FastAPI). Cada tarefa tem um `background_job` com status e progresso. O frontend acompanha por **SSE** e cai automaticamente para **polling** quando o SSE não funciona.

## Consequências
- Mais leve que Celery; um único worker no perfil `lite`.
- O fallback de polling é testado explicitamente.
