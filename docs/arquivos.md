# Arquivos grandes

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

### 10.7 Arquivos grandes
- **Upload direto ao armazenamento:** o backend gera URLs assinadas e o navegador envia o arquivo **em partes** (multipart, ~8 a 16 MB por parte) direto ao MinIO, sem passar o arquivo pelo FastAPI. Se a conexão cair, o envio **retoma** das partes que faltam (`upload_session`).
- Limite por PDF configurável (padrão **100 MB**); limite total por projeto e por usuário conforme as cotas (6).
- **Deduplicação por hash:** o mesmo PDF enviado duas vezes é guardado uma vez só (`stored_file` com `ref_count`).
- O banco guarda só metadados (nome, hash, tamanho, tipo), nunca o conteúdo.
- **Visualização progressiva:** PDF.js com requisições por faixa (HTTP Range); um PDF de 80 MB abre sem baixar tudo.
- **Processamento em segundo plano** (worker): extração de texto, contagem de páginas, verificação de tipo real e, na P2, OCR (`ocrmypdf`) de PDFs escaneados, com progresso na tela.
- **Importações grandes** (milhares de referências, planilhas grandes) lidas em fluxo e gravadas em lotes; relatório de erros por linha sem parar a importação inteira.
- **Exportações grandes** (ZIP do projeto, todos os PDFs) geradas pelo worker como arquivo e baixadas por URL assinada, nunca montadas na memória da requisição.
- Painel de uso de espaço por projeto e por usuário.
- Testes com arquivos grandes sintéticos (ex.: PDF de 100 MB, RIS com 20 mil registros) e com queda de conexão no meio do upload.
