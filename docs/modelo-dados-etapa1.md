# Modelo de dados — Etapa 1 (proposta para aprovação)

> Refina o rascunho da seção 9 ([modelo-dados.md](modelo-dados.md)) para a Etapa 1: protocolo mínimo, estudos, relatos, PDFs, extração e proteções anti-erro (7.5.1 blocos A, C, D, F e G).
> Todas as tabelas de negócio têm `id` (UUID v7), `project_id`, `created_at`, `updated_at`, `created_by`, `deleted_at` (soft delete) e `version` (trava otimista), omitidos no diagrama.

## Diagrama

```mermaid
erDiagram
    projects ||--o{ outcomes : "define"
    projects ||--o{ comparison_groups : "define"
    projects ||--o{ studies : "tem"
    projects ||--o{ extraction_forms : "versiona"

    studies ||--o{ reports : "agrupa artigos"
    references ||--o{ reports : "é publicado como"
    reports ||--o{ pdf_files : "anexa"
    stored_files ||--o{ pdf_files : "conteúdo"
    stored_files ||--o{ pdf_page_texts : "texto por página"
    pdf_files ||--o{ pdf_annotations : "trechos marcados"

    studies ||--o{ extractions : "2 individuais + 1 consenso"
    extraction_forms ||--o{ extractions : "versão usada"
    extractions ||--o{ study_arms : "braços do estudo"
    extractions ||--o{ outcome_measures : "escala por desfecho"
    extractions ||--o{ outcome_data : "números"
    study_arms ||--o{ outcome_data : "por braço"
    outcomes ||--o{ outcome_data : "de qual desfecho"
    comparison_groups ||--o{ study_arms : "mapeado para"
    pdf_annotations ||--o{ outcome_data : "fonte no PDF"
    extractions ||--o{ check_alerts : "alertas"

    outcomes {
        string name
        enum type "continuous | dichotomous"
        bool higher_is_better "padrão; a escala do estudo pode inverter"
        bool is_primary
        string[] timepoints "ex.: 12 meses, 5 anos"
    }
    comparison_groups {
        string label "ex.: Cirurgia < 5 anos"
        text rule_description
        int position
    }
    references {
        string title
        string authors
        int year
        string doi "normalizado"
        string pmid
        string journal
    }
    studies {
        string label "ex.: Ballet 2025, único no projeto"
        enum design "ECR, coorte prosp./retrosp., caso-controle, transversal, série de casos, outro"
        text notes
    }
    reports {
        bool is_primary
    }
    pdf_files {
        string original_filename
        int page_count
        enum text_status "pending | ready | failed | no_text"
    }
    pdf_page_texts {
        int page
        text content "para busca e, depois, conferência de citações da IA"
    }
    pdf_annotations {
        int page
        jsonb rects "posição do destaque"
        text quote "texto marcado"
        text note
    }
    extraction_forms {
        int version
        jsonb schema "campos de características (construtor de formulário)"
        bool is_current
    }
    extractions {
        uuid extractor_id
        enum kind "individual | consensus"
        enum status "draft | submitted | locked"
        jsonb characteristics "respostas do formulário"
        int data_version "sobe a cada mudança em números (bloco G)"
    }
    study_arms {
        string label "como o estudo chama o grupo"
        int n
        text description
        uuid mapped_group_id "grupo de comparação do protocolo; nulo se o estudo tiver mais braços"
    }
    outcome_measures {
        string scale_name "ex.: WISC-IV, Bayley-III"
        numeric scale_min
        numeric scale_max
        bool higher_is_better "define a direção (inversão só no R, Etapa 3)"
    }
    outcome_data {
        string timepoint
        enum value_type "final | change"
        int n
        numeric mean
        enum dispersion_type "sd | se | ci95 | iqr | range | not_reported (obrigatório)"
        string dispersion_source "onde o artigo diz o tipo, ex.: rodapé da Tabela 2"
        numeric sd_se_ci_median_q1_q3_min_max "colunas separadas"
        int events_total "dicotômico"
        numeric t_stat_p_value
        jsonb effect_reported "efeito + IC já calculado (OR/HR ajustado)"
        bool adjusted
        string adjusted_for
        enum source "article | author | digitizer | ai"
        string source_location "página/tabela"
        bool direction_confirmed "frase de conferência confirmada (bloco C)"
    }
    check_alerts {
        string code "ex.: extraction.ci_excludes_mean"
        enum severity "block | warn"
        string target_field
        enum status "open | justified | resolved"
        text justification "obrigatória para dispensar"
    }
```

## Decisões de modelagem

1. **Dupla extração (decidido: obrigatória, padrão ligado).** Cada estudo tem até **duas extrações individuais** (`kind = individual`, uma por extrator) e **uma de consenso** (`kind = consensus`). As individuais ficam cegas entre si até as duas serem enviadas. A configuração fica em `projects.settings.double_extraction` (o admin pode desligar; desligado, a extração única vira o consenso ao ser enviada).
2. **Digitar uma vez (bloco G).** Análises, exportações e o painel leem **só** a extração de consenso. Qualquer mudança em números dela incrementa `extractions.data_version`; na Etapa 3 cada análise guarda a versão usada e fica "desatualizada" quando ela muda.
3. **Braços por extração.** O `n` de cada braço também é número de desfecho e entra na comparação campo a campo; por isso os braços pertencem à extração, não ao estudo. Estudos com mais de dois braços registram todos; a combinação em dois grupos é feita pelo R na Etapa 3 (fórmula do Cochrane), nunca à mão.
4. **Escala por estudo e desfecho** (`outcome_measures`): estudos medem cognição com escalas diferentes; faixa e direção ficam ali e alimentam o alerta "fora da escala" e a frase de direção.
5. **Alertas persistidos** (`check_alerts`): cada alerta tem estado; dispensar exige justificativa e vai para a auditoria. A lista "Pendências de conferência" e a trava da etapa (bloco F) leem daqui. Os alertas são recalculados quando o dado muda.
6. **Referência mínima agora.** `references` nasce com os campos da lista final (título, autores, ano, DOI, PMID, revista). Importação RIS/BibTeX, buscas e triagem completam a tabela na Etapa 5.
7. **Texto do PDF por arquivo físico.** `pdf_page_texts` liga ao `stored_file` (o mesmo PDF enviado duas vezes é extraído uma vez só), com **pypdfium2** (ADR-012).
8. **Isolamento.** Toda tabela tem `project_id`, inclusive as filhas, para que toda consulta filtre por projeto e o teste de isolamento cubra cada rota nova.

## Fora desta etapa (já previsto no modelo)
- Conversões, combinação de braços, detector de EP e influência (blocos B e E) → Etapa 3, no serviço R.
- Inversão de sinal de escalas "maior é pior" → Etapa 3, só no R.
- Contato com autores, motivos de exclusão, triagem → Etapas 5 e 6.
