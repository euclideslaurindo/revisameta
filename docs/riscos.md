# Segurança, privacidade e confiabilidade

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

## 10. Requisitos não funcionais

### 10.1 Segurança
- JWT de curta duração + refresh token rotativo; logout invalida o refresh.
- Senhas com bcrypt/argon2; política mínima de senha.
- Autorização por **papel e por projeto** em todo endpoint (dependência do FastAPI reutilizável).
- Upload: só PDF (checar tipo real, não só a extensão), limite de tamanho, hash SHA-256, nome de arquivo gerado pelo sistema (evita path traversal).
- CORS restrito ao domínio do frontend; rate limiting no login.
- Segredos só em `.env`; `.env.example` sem valores reais.
- Cabeçalhos de segurança (CSP, HSTS quando houver HTTPS próprio, X-Content-Type-Options, frame-ancestors).
- PDFs exibidos sem executar JavaScript embutido; arquivos servidos só por URL assinada de curta duração.
- Captcha (Turnstile) no cadastro e após falhas de login; verificação de e-mail obrigatória.
- Varredura de dependências no CI (Dependabot, `pip-audit`, `npm audit`) e de segredos (`gitleaks`).
- Chaves de API de IA só no servidor, nunca no frontend.
- 2FA opcional (P2).
- **Postgres, Redis e MinIO nunca expostos** para fora da rede do Docker.

### 10.2 Privacidade (LGPD)
- Os dados dos estudos são agregados e publicados, mas há dados de usuários: coletar o mínimo, permitir exclusão da conta e exportação do projeto.
- Termos de uso e aviso de privacidade simples antes de publicar.
- PDFs ficam no projeto e só membros acessam (URLs assinadas ou rota autenticada). **PDFs de artigos têm direito autoral: nunca ficam públicos**, nem por link compartilhável.
- Como o sistema é aberto ao público: **termos de uso e política de privacidade** (pt e en) aceitos no cadastro, com versão registrada; exclusão de conta e exportação de dados pelo próprio usuário; prazo de retenção de projetos inativos definido (10.8).
- Aviso claro sobre o envio de dados a provedores de IA (7.15.5).

**Implementado:** páginas públicas `/termos` e `/privacidade` (pt e en, texto em `frontend/public/i18n/*.json`, chave `legal`). A controladora dos dados é a **B-TECH** (provisório). A versão fica em `backend/app/core/legal.py` (`TERMS_VERSION`): ao mudar o texto de forma relevante, aumente a versão; quem aceitou uma versão anterior é levado a `/aceitar-termos` antes de continuar, e o aceite fica registrado no usuário (auditoria). O e-mail de contato (LGPD e remoção por direitos autorais) vem de `LEGAL_CONTACT_EMAIL` no `.env`; sem ele, as páginas mostram "e-mail de contato ainda não definido". Recuperação de senha por e-mail (link de 1 hora, uso único, encerra todas as sessões) e troca de senha no perfil (encerra as outras sessões).

No perfil, a pessoa baixa os próprios dados (JSON: conta, projetos e comentários) e exclui a conta. A exclusão pede a senha (e o código de 2FA, se ligado), **anonimiza** a conta (nome, e-mail, senha e 2FA apagados; sai de todas as sessões), encerra as participações e apaga (soft delete) os projetos em que a pessoa estava sozinha. Se ela for dona de um projeto com outros membros, ou a única administradora, precisa antes passar a administração; assim ninguém perde uma revisão compartilhada. O trabalho já feito fica no projeto, sem o nome dela.

**Administração do sistema** (`/admin`, só para quem tem `is_system_admin`): situação dos serviços, resumo de contas e projetos, lista de usuários com busca, suspender/reativar conta (desconecta na hora), dar/tirar administração (nunca da própria conta) e ajustar cotas por pessoa. Não dá acesso ao conteúdo dos projetos. O primeiro administrador é criado com `scripts/make-admin.sh <e-mail>`.

---

### 10.4 Desempenho e confiabilidade
- Triagem fluida com milhares de referências (paginação e carregamento sob demanda).
- Tarefas longas na fila com indicador de progresso.
- Backup diário do banco e dos arquivos; procedimento de restauração testado.
- Nenhuma exclusão definitiva de decisões (soft delete).

### 10.5 Observabilidade
- Logs estruturados (JSON) com id de requisição propagado do Python ao R.
- Healthcheck de todos os serviços; página de status para o admin.
