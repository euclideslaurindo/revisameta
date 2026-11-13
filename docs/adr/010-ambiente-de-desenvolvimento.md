# ADR-010: Ambiente de desenvolvimento local

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
A máquina de desenvolvimento é Windows com Docker e Node, sem R, `uv`, `make` nem `cloudflared`. Na F0 não há servidor de e-mail nem conta Cloudflare.

## Decisão
- **R e Python/uv rodam só em containers**; os testes do backend e do R são executados com `docker compose run`.
- **Scripts em `scripts/*.sh`** (rodam no Git Bash e no Linux). Um `Makefile` fino só chama esses scripts, para quem tiver `make` (ex.: servidor da F1).
- **Mailpit** no Compose recebe todos os e-mails no desenvolvimento (caixa em `http://localhost:8025`).
- **Turnstile desligável** por `TURNSTILE_ENABLED`; o `.env.example` traz as chaves públicas de teste da Cloudflare.
- **cloudflared** roda como container no `scripts/tunnel.sh`, sem instalar nada no Windows.
- Angular na versão LTS vigente quando o projeto for criado.

## Consequências
- Para desenvolver, só é preciso ter Docker, Git e Node instalados.
