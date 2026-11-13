# RevisaMeta

> 🇧🇷 [Português](#português) · 🇺🇸 [English](#english)

---

## Português

Plataforma web gratuita para **revisões sistemáticas com meta-análise**, pensada para pesquisadores iniciantes. Reúne em um só lugar protocolo, importação, triagem, extração de dados, risco de viés, meta-análise, GRADE e PRISMA, com proteções contra os erros de extração mais comuns.

> **Versão beta**, sem garantia de disponibilidade.

### Requisitos

- Docker com Docker Compose v2
- Git (no Windows, use o Git Bash para os scripts em `scripts/`)

R, Python e Node rodam dentro dos containers; não é preciso instalá-los para subir o sistema.

### Primeiros passos

```bash
git clone https://github.com/euclideslaurindo/revisameta.git
cd revisameta
git config core.hooksPath .githooks   # ativa o hook de commits
cp .env.example .env                  # depois troque os valores marcados como "change-me"
docker compose up -d
```

Máquinas com pouca memória: `docker compose --profile lite up -d`.

### Documentação

- [CLAUDE.md](CLAUDE.md): regras do projeto, stack, estrutura e mapa da documentação
- [docs/](docs/): especificação por tema
- [docs/adr/](docs/adr/): decisões de arquitetura

### Licença

Ainda não definida (o repositório é privado). Será escolhida antes de qualquer abertura pública.

---

## English

Free web platform for **systematic reviews with meta-analysis**, designed for first-time researchers. It brings protocol, import, screening, data extraction, risk of bias, meta-analysis, GRADE and PRISMA into one place, with safeguards against the most common data extraction errors.

> **Beta version**, no availability guarantee.

### Requirements

- Docker with Docker Compose v2
- Git (on Windows, use Git Bash for the scripts in `scripts/`)

R, Python and Node run inside the containers; you do not need them installed to start the system.

### Getting started

```bash
git clone https://github.com/euclideslaurindo/revisameta.git
cd revisameta
git config core.hooksPath .githooks   # enables the commit hook
cp .env.example .env                  # then replace the values marked "change-me"
docker compose up -d
```

Low-memory machines: `docker compose --profile lite up -d`.

### Documentation

- [CLAUDE.md](CLAUDE.md): project rules, stack, structure and documentation map (Portuguese)
- [docs/](docs/): specification by topic (Portuguese)
- [docs/adr/](docs/adr/): architecture decision records

### License

Not defined yet (the repository is private). It will be chosen before any public release.
