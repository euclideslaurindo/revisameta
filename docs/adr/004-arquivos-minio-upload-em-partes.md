# ADR-004: Arquivos no MinIO com upload direto em partes e deduplicação por hash

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
PDFs podem ter até 100 MB, a internet do desenvolvedor na F0 é limitada, a Cloudflare gratuita limita cada requisição a 100 MB e o backend não pode carregar arquivos grandes na memória.

## Decisão
MinIO (compatível com S3) no Compose. O backend cria uma `upload_session` e gera URLs assinadas por parte (multipart, ~10 MB); o navegador envia as partes **direto ao armazenamento** e pode retomar as que faltam depois de uma queda. O banco guarda só metadados. O mesmo conteúdo (SHA-256) é guardado uma vez só (`stored_file` com `ref_count`). Arquivos são servidos só por URL assinada de curta duração; PDFs nunca ficam públicos.

## Consequências
- O FastAPI nunca recebe o corpo do arquivo; a verificação do tipo real e a extração de texto rodam no worker.
- Migrar para qualquer S3 (B2, R2, AWS) só muda configuração.
- O navegador acessa o MinIO pelo Caddy (`/storage`), sem expor o MinIO diretamente.
