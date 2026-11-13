# Modelo de dados

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

## 9. Modelo de dados (rascunho — refinar e propor diagrama ER antes de implementar)

Toda tabela de negócio tem: `id` (UUID), `project_id` (quando aplicável), `created_at`, `updated_at`, `created_by`, `deleted_at` (soft delete) e `version` (**trava otimista**: duas pessoas editando o mesmo registro não sobrescrevem uma à outra).

```
user(id, name, email, password_hash, is_active)
project(id, title, question, pico_jsonb, prospero, deadline, analysis_plan_jsonb, locked_stages[])
project_member(project_id, user_id, roles[])
invitation(id, project_id, email, roles[], token_hash, expires_at, accepted_at)
protocol_amendment(id, project_id, description, reason, approved_by, date)
criterion(id, project_id, kind[inclusion|exclusion], text, order)
outcome(id, project_id, name, type[continuous|dichotomous], higher_is_better, primary, timepoints[])
comparison_group(id, project_id, label, rule_description)        -- ex.: "< 5 anos"

search(id, project_id, database, search_date, strategy)
reference(id, project_id, search_id, title, abstract, authors, year, doi, journal, duplicate_of)
screening_decision(id, reference_id, user_id, stage[title_abstract|full_text], decision, exclusion_reason)
conflict(id, project_id, entity, entity_id, status, resolved_by, resolution)

study(id, project_id, label, design)                                -- ex.: "Ballet 2025"
report(id, study_id, reference_id, is_primary)                      -- vários artigos → um estudo
pdf_file(id, reference_id, storage_key, sha256, uploaded_by)
pdf_annotation(id, pdf_id, user_id, page, coords_jsonb, text, color)
author_contact(id, study_id, requested, sent_at, answered_at, notes)

extraction_form(id, project_id, version, schema_jsonb)
extraction(id, study_id, form_id, user_id, data_jsonb, status, is_consensus)
study_arm(id, study_id, label, n, description, mapped_group_id)    -- braços originais do estudo
outcome_data(id, study_id, outcome_id, arm_id, timepoint, value_type[final|change],
             n, mean, sd, se, ci_low, ci_high, median, q1, q3, min, max, events, total,
             t_stat, p_value, effect_reported_jsonb, adjusted, adjusted_for,
             converted_jsonb, conversion_method, source[article|author|digitizer|ai],
             source_page, annotation_id, extracted_by, confirmed)

rob_tool(id, name, version, target_design, template_jsonb)
rob_assessment(id, study_id, outcome_id NULL, timepoint NULL, tool_id, user_id, status)
rob_answer(id, assessment_id, domain, question, answer, justification, annotation_id)
rob_judgement(id, assessment_id, domain NULL, suggested, final, justification)   -- domain NULL = geral
rob_consensus(id, study_id, outcome_id NULL, tool_id, domain NULL, judgement, decided_by, reason)

analysis(id, project_id, outcome_id, timepoint, measure, model, estimator, ci_method,
         filters_jsonb, included_study_ids[], input_snapshot_jsonb, result_jsonb,
         r_meta_jsonb, planned, created_by)
figure(id, project_id, analysis_id NULL, kind, format, storage_key)

grade_assessment(id, project_id, outcome_id, start_certainty, approach, adjustments_jsonb, final_certainty, justification)
prisma_count(project_id, key, value, manually_adjusted, justification)
prisma_checklist_item(project_id, item_code, status, location_in_manuscript)
comment(id, project_id, entity, entity_id, user_id, text)
notification(id, user_id, project_id, kind, payload_jsonb, read_at)
audit_log(id, project_id, entity, entity_id, field, old_value, new_value, user_id, created_at)

stored_file(id, sha256, size_bytes, mime, storage_key, ref_count)       -- deduplicação por hash (10.7)
upload_session(id, user_id, project_id, filename, size_bytes, parts_done, status, expires_at)
background_job(id, project_id, kind, status, progress, result_jsonb, error, created_by)
usage_quota(user_id, kind, period, used, limit)                         -- projetos, armazenamento, IA
ai_settings(project_id, enabled, provider, accepted_terms_by, accepted_at, functions_enabled[])
ai_suggestion(id, project_id, task[tutor|locate|extract|rob|search|draft], target_entity, target_id,
              payload_jsonb, quote, page, quote_verified, prompt_version, provider, model,
              status[suggested|accepted|corrected|rejected|discarded], decided_by, decided_at)
user_preference(user_id, ui_language[pt-BR|en], number_format)
```
