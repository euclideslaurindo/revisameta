# ADR-001: Backend em Python + FastAPI

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
O backend faz muito I/O (banco, armazenamento, serviço R, fila) e precisa de bibliotecas maduras para importar referências (RIS, BibTeX, nbib), ler PDFs, ler e gerar planilhas e documentos, e integrar provedores de IA.

## Decisão
Python 3.12 com FastAPI, Pydantic v2, SQLAlchemy 2.0 assíncrono (asyncpg) e Alembic. Módulos por domínio (`router` → `service` → `repository`). Dependências gerenciadas com `uv`, com versões fixadas.

## Consequências
- Ecossistema forte para dados, PDFs e IA; OpenAPI gerado automaticamente, de onde sai o cliente TypeScript do frontend.
- Exige disciplina de tipos (`mypy`) e lint (`ruff`), verificados no CI.
- Estatística não é feita aqui (ver ADR-002).
