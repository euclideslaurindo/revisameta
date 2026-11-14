# ADR-012: Leitura de PDF no servidor com pypdfium2 (no lugar do PyMuPDF)

**Status:** Aceito · **Data:** 2026-11-14

## Contexto
O servidor precisa do texto de cada página dos PDFs (busca, número de páginas e, na Etapa 7, conferência das citações da IA). A especificação sugeria o **PyMuPDF**, que é licenciado como **AGPL-3.0** (ou licença comercial da Artifex). Num sistema aberto ao público pela internet, a AGPL obriga a disponibilizar o código-fonte do RevisaMeta aos usuários. A licença do projeto ainda não foi decidida (seção 17, pergunta 14).

## Decisão
Usar **pypdfium2** (BSD-3-Clause/Apache-2.0), que expõe o PDFium (motor de PDF do Chrome): texto por página com posições, contagem de páginas e renderização. O visualizador no navegador é o `ngx-extended-pdf-viewer` (Apache-2.0, PDF.js).

## Consequências
- Nenhuma obrigação de licença imposta ao projeto pela leitura de PDF.
- PDFs escaneados (sem camada de texto) ficam marcados como `no_text`; OCR continua na Etapa 8 (`ocrmypdf`, MPL-2.0).
