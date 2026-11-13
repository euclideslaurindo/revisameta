# ADR-006: Autenticação

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
O sistema é aberto ao público (cadastro livre) e guarda dados não publicados de pesquisa. Tokens no `localStorage` ficam expostos a XSS.

## Decisão
- Access token JWT curto, guardado **só em memória** no frontend.
- Refresh token **rotativo** em cookie `httpOnly`, `SameSite=Strict` e `Secure` quando houver HTTPS; guardado como hash no banco; logout e reuso de token antigo invalidam a família inteira.
- Senhas com **Argon2id** (`argon2-cffi`). A seção 10.1 cita bcrypt como alternativa; fica decidido Argon2id.
- Cadastro com verificação de e-mail e captcha Cloudflare Turnstile (desligável por variável de ambiente no desenvolvimento); rate limiting no login.

## Consequências
- Ao abrir o app, o frontend faz um `refresh` silencioso para recuperar a sessão.
- Na F0 os e-mails de verificação vão para o Mailpit (ADR-010).
