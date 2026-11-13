# ADR-004: Arquivos em armazenamento S3 (RustFS) com upload direto em partes e deduplicação por hash

**Status:** Aceito · **Data:** 2026-11-13 · **Revisado:** 2026-11-13 (MinIO → RustFS)

## Contexto
PDFs podem ter até 100 MB, a internet do desenvolvedor na F0 é limitada, a Cloudflare gratuita limita cada requisição a 100 MB e o backend não pode carregar arquivos grandes na memória.

A especificação previa o **MinIO**. Ao montar a Etapa 0 (nov/2026), o projeto MinIO estava descontinuado: repositório arquivado no GitHub (última versão em outubro de 2025) e imagem removida do Docker Hub. Usá-lo exigiria compilar uma versão que não recebe mais correções de segurança.

## Decisão
- Armazenamento **RustFS** (`rustfs/rustfs`, Apache-2.0, compatível com a API S3 e com o jeito de configurar do MinIO, imagens amd64 e arm64), versão fixada no Compose. Alternativas avaliadas: Garage (AGPL, leve, mas exige configuração inicial de layout e chaves), MinIO compilado (sem correções de segurança) e SeaweedFS (mais pesado do que precisamos).
- O backend fala **só a API S3** (`aioboto3`), sem nada específico do RustFS. Trocar de servidor (Garage, B2, R2, AWS) muda apenas variáveis de ambiente.
- O backend cria uma `upload_session` e gera URLs assinadas por parte (multipart, ~10 MB); o navegador envia as partes **direto ao armazenamento** e pode retomar as que faltam depois de uma queda. O banco guarda só metadados.
- O mesmo conteúdo (SHA-256) é guardado uma vez só (`stored_file` com `ref_count`).
- Arquivos são servidos só por URL assinada de curta duração; PDFs nunca ficam públicos.
- O navegador acessa o armazenamento pelo Caddy, no caminho `/<bucket>/...` da mesma origem do sistema. O Caddy preserva o `Host` e o caminho, então a assinatura continua válida, e o RustFS nunca fica exposto diretamente. Por isso `S3_PUBLIC_ENDPOINT` deve ser a mesma origem que os usuários abrem (endereço do túnel ou domínio).

## Consequências
- O FastAPI nunca recebe o corpo do arquivo; a verificação do tipo real e a extração de texto rodam no worker.
- O RustFS é mais novo que o MinIO: acompanhar as versões e manter o backup diário (10.8) independente do servidor de armazenamento.
