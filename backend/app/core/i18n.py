"""Backend messages in pt-BR and en (ADR-008).

Every user-facing message (errors, e-mails) is looked up here by a stable code.
A test guarantees both languages define exactly the same codes.
"""

from typing import Literal

Language = Literal["pt-BR", "en"]
DEFAULT_LANGUAGE: Language = "pt-BR"
SUPPORTED_LANGUAGES: tuple[Language, ...] = ("pt-BR", "en")

MESSAGES: dict[Language, dict[str, str]] = {
    "pt-BR": {
        "error.internal": "Ocorreu um erro inesperado. Tente de novo em instantes.",
        "error.validation": "Alguns campos estão inválidos. Confira os dados enviados.",
        "error.not_found": "O item procurado não existe ou você não tem acesso a ele.",
        "error.not_authenticated": "Você precisa entrar na sua conta para continuar.",
        "error.forbidden": "Você não tem permissão para fazer isso neste projeto.",
        "error.version_conflict": (
            "Outra pessoa alterou este item enquanto você editava. "
            "Recarregue para ver a versão mais recente."
        ),
        "error.rate_limited": "Muitas tentativas. Aguarde um pouco e tente de novo.",
        "error.stats_failed": "O serviço de estatística não conseguiu gerar o resultado.",
        "error.stats_unavailable": (
            "O serviço de estatística está fora do ar no momento. Nada foi salvo. "
            "Tente de novo em alguns minutos."
        ),
        "auth.email_taken": "Já existe uma conta com este e-mail.",
        "auth.invalid_credentials": "E-mail ou senha incorretos.",
        "auth.email_not_verified": (
            "Confirme seu e-mail antes de entrar. Veja sua caixa de entrada."
        ),
        "auth.account_disabled": "Esta conta está desativada.",
        "auth.weak_password": (
            "A senha precisa ter pelo menos 10 caracteres, com letras e números."
        ),
        "auth.captcha_failed": "Não foi possível confirmar que você não é um robô. Tente de novo.",
        "auth.terms_required": "É preciso aceitar os termos de uso e a política de privacidade.",
        "auth.invalid_token": "Este link é inválido ou expirou.",
        "auth.session_expired": "Sua sessão expirou. Entre novamente.",
        "project.creator_cannot_be_removed": (
            "O criador do projeto não pode ser removido sem antes transferir a administração."
        ),
        "project.last_admin": "O projeto precisa ter pelo menos um administrador.",
        "project.already_member": "Esta pessoa já é membro do projeto.",
        "protocol.duplicate_name": "Já existe um item com este nome no protocolo do projeto.",
        "study.duplicate_label": "Já existe um estudo com este nome no projeto.",
        "pdf.upload_not_ready": "O envio deste PDF ainda não terminou. Aguarde o processamento e tente de novo.",
        "extraction.not_editable": "Esta extração já foi enviada e não pode mais ser alterada.",
        "extraction.impossible.n_not_positive": "O n (ou o total) precisa ser maior que zero.",
        "extraction.impossible.sd_not_positive": "O DP precisa ser maior que zero.",
        "extraction.impossible.se_not_positive": "O EP precisa ser maior que zero.",
        "extraction.impossible.negative_events": "O número de eventos não pode ser negativo.",
        "extraction.impossible.events_gt_total": "O número de eventos não pode ser maior que o total do grupo.",
        "extraction.impossible.ci_inverted": "O limite inferior do IC não pode ser maior que o superior.",
        "extraction.impossible.iqr_inverted": "O 1º quartil não pode ser maior que o 3º.",
        "extraction.impossible.range_inverted": "O mínimo não pode ser maior que o máximo.",
        "extraction.impossible.median_outside": "A mediana precisa estar entre os quartis (ou entre o mínimo e o máximo).",
        "extraction.alert_resolved": "Este alerta já foi resolvido com a correção do valor.",
        "extraction.alert_confirm_direction": (
            "Este alerta é resolvido confirmando a frase de direção do efeito."
        ),
        "extraction.impossible.ratio_not_positive": "OR, RR e HR são sempre maiores que zero (estimativa e IC). Confira o valor digitado.",
        "extraction.impossible.p_out_of_range": "O valor p precisa estar entre 0 e 1.",
        "rob.tool_in_use": "Este instrumento já tem avaliações; a estrutura não pode mais mudar.",
        "rob.study_has_assessments": "Este estudo já tem avaliações com outro instrumento, que não pode mais ser trocado.",
        "rob.has_official_rule": "Este instrumento tem regra oficial para o julgamento geral.",
        "rob.invalid_rule": "A regra do grupo tem algum erro: confira os níveis, as respostas e as perguntas usadas.",
        "rob.no_tool_confirmed": "O administrador ainda não confirmou o instrumento deste estudo.",
        "rob.result_required": "Este instrumento avalia por resultado: escolha o desfecho e o momento.",
        "rob.unknown_result": "Este desfecho ou momento não existe no protocolo.",
        "rob.enough_reviewers": "Este estudo já tem {limit} avaliações individuais para este resultado.",
        "rob.not_editable": "Esta avaliação já foi enviada e não pode mais ser alterada.",
        "rob.invalid_answer": "Resposta inválida para a pergunta {key}.",
        "rob.wrong_target": "A pergunta {key} é respondida em outro nível (estudo, desfecho ou resultado).",
        "rob.unknown_annotation": "Este trecho não é de um PDF deste estudo.",
        "rob.unknown_variant": "Variante inválida para o domínio {key}.",
        "rob.no_domain_judgement": "Neste instrumento não há julgamento por domínio, só o geral.",
        "rob.unknown_domain": "O domínio {key} não existe neste instrumento.",
        "rob.invalid_judgement": "Julgamento inválido para este instrumento.",
        "rob.invalid_direction": "Direção do viés inválida para este instrumento.",
        "rob.consensus_waiting": "O consenso só pode ser criado depois que as duas avaliações individuais forem enviadas.",
        "rob.consensus_exists": "Esta avaliação já tem um consenso.",
        "rob.not_a_conflict": "Este item não é um conflito entre os dois revisores.",
        "rob.reason_required": "Explique em poucas palavras por que o consenso é diferente dos dois revisores.",
        "rob.undecided_conflicts": "Ainda há {count} conflito(s) sem decisão. Decida todos antes de enviar o consenso.",
        "rob.nothing_to_plot": "Nenhum estudo tem consenso enviado para este instrumento e resultado; não há o que desenhar.",
        "rob.plot_missing_studies": "{count} estudo(s) ainda sem consenso enviado ficariam de fora do gráfico. Confirme para gerar mesmo assim.",
        "rob.no_robvis_template": "O robvis não tem modelo para este instrumento; use CSV, XLSX ou DOCX.",
        "rob.nothing_to_export": "Nenhum estudo tem consenso enviado para este instrumento e resultado; não há o que exportar.",
        "rob.export_missing_studies": "{count} estudo(s) ainda sem consenso enviado ficariam de fora do arquivo. Confirme para exportar mesmo assim.",
        "rob_import.invalid_mapping": "Confira a correspondência das colunas: estudo, julgamento geral e (exceto em checklists) todos os domínios são obrigatórios.",
        "rob.review_not_ready": "A etapa só pode ser travada com todos os estudos concluídos ({ready} de {total}).",
        "rob.reopen_only_consensus": "Só um consenso pode ser reaberto. Para corrigir uma importação, descarte-a e importe de novo.",
        "rob.not_submitted": "Esta avaliação não está enviada.",
        "rob.discard_only_import": "Só uma avaliação importada pode ser descartada.",
        "plan.unknown_group": "O grupo escolhido não existe no protocolo.",
        "plan.unknown_outcome": "O desfecho escolhido não existe no protocolo.",
        "plan.measure_mismatch": 'A medida de efeito não combina com o tipo do desfecho "{outcome}".',
        "plan.unknown_timepoint": 'O momento escolhido não existe no desfecho "{outcome}".',
        "analysis.unknown_result": "Este desfecho não tem o momento escolhido.",
        "analysis.measure_mismatch": "A medida de efeito não combina com o tipo do desfecho.",
        "analysis.blocked": "A análise não pode rodar: {blocks}. Veja os motivos no passo 1.",
        "rob.incomplete": "Ainda faltam {count} item(ns) para enviar a avaliação.",
        "rob.unknown_template": "Este instrumento não existe no catálogo.",
        "rob.already_enabled": "Este instrumento, nesta versão, já está habilitado no projeto.",
        "rob.unknown_question": 'A pergunta "{key}" não existe neste instrumento.',
        "rob.text_too_long": 'O texto da pergunta "{key}" está longo demais.',
        "rob.not_generic": "Só o instrumento genérico tem domínios definidos pelo grupo.",
        "export.empty": "Não há dados para exportar: nenhum estudo tem consenso enviado. Use a opção de extrações individuais (pré-consenso) se precisar.",
        "export.incomplete": "{count} estudo(s) ficariam fora do arquivo. Confira a lista e confirme a exportação.",
        "stage.locked": "Esta etapa está travada. Peça ao administrador para destravá-la (com justificativa) se precisar alterar algo.",
        "stage.not_locked": "Esta etapa não está travada.",
        "review.not_ready": "Só dá para travar quando todos os estudos têm consenso enviado e nenhum alerta em aberto ({ready} de {total} prontos).",
        "review.not_a_consensus": "Consenso não encontrado.",
        "review.not_submitted": "Só um consenso enviado pode ser reaberto.",
        "consensus.exists": "Este estudo já tem um consenso.",
        "consensus.waiting_extractions": "O consenso só pode ser criado depois que {needed} extração(ões) individual(is) forem enviadas.",
        "consensus.missing": "Crie o consenso antes de decidir as divergências.",
        "consensus.not_double": "Este estudo não tem duas extrações para comparar.",
        "consensus.not_a_divergence": "Este campo não é uma divergência entre os dois extratores.",
        "consensus.reason_required": "Explique em poucas palavras por que o valor do consenso é diferente dos dois extratores.",
        "consensus.undecided_divergences": "Ainda há {count} divergência(s) sem decisão. Decida todas antes de enviar o consenso.",
        "extraction.open_blocking_alerts": "Há alertas que impedem o envio. Corrija os valores ou justifique os alertas antes de enviar.",
        "extraction.enough_extractors": "Este estudo já tem {limit} extrator(es). Peça ao administrador para ajustar, se precisar.",
        "extraction.invalid_field": 'O campo "{field}" tem um valor inválido.',
        "extraction.unknown_group": "Este grupo de comparação não existe no protocolo do projeto.",
        "extraction.arm_in_use": "Este grupo tem números de desfecho registrados. Apague esses números antes de remover o grupo.",
        "extraction.unknown_outcome": "Este desfecho não existe no protocolo do projeto.",
        "extraction.invalid_scale_range": "O valor mínimo da escala precisa ser menor que o máximo.",
        "extraction.unknown_annotation": "O trecho escolhido não é de um PDF deste estudo.",
        "extraction.unknown_arm": "Este grupo não pertence a esta extração.",
        "extraction.unknown_timepoint": "Este momento de medida não está no protocolo do desfecho.",
        "study.duplicate_doi": "Já existe um artigo com este DOI no projeto.",
        "study.last_report": "Um estudo precisa de pelo menos um artigo. Para tirá-lo da revisão, exclua o estudo.",
        "import.too_large": "O arquivo passa do limite de {limit} MB.",
        "import.unsupported_format": "Formato não aceito. Envie uma planilha .xlsx ou um arquivo .csv.",
        "import.empty_file": "O arquivo está vazio ou sem a linha de cabeçalho.",
        "import.invalid_mapping": "Confira a correspondência das colunas: o título é obrigatório.",
        "import.too_many_rows": "O arquivo passa do limite de {limit} linhas.",
        "invitation.expired": "Este convite expirou. Peça um novo ao administrador do projeto.",
        "invitation.already_accepted": "Este convite já foi usado.",
        "invitation.wrong_email": "Este convite foi enviado para outro e-mail.",
        "quota.projects_exceeded": (
            "Você atingiu o limite de {limit} projetos. "
            "Arquive um projeto ou peça mais espaço ao administrador do sistema."
        ),
        "quota.storage_exceeded": (
            "Você atingiu o limite de armazenamento ({limit} MB). "
            "Remova arquivos ou peça mais espaço ao administrador do sistema."
        ),
        "upload.too_large": "O arquivo passa do limite de {limit} MB.",
        "upload.not_pdf": "Só são aceitos arquivos PDF.",
        "upload.incomplete": "Ainda faltam partes do arquivo. Continue o envio.",
        "upload.expired": "Este envio expirou. Comece de novo.",
        "email.verify.subject": "Confirme seu e-mail no RevisaMeta",
        "email.verify.body": (
            "Olá, {name}!\n\nPara confirmar seu e-mail, abra o link abaixo:\n{link}\n\n"
            "O link vale por 48 horas. Se você não criou esta conta, ignore esta mensagem."
        ),
        "email.invite.subject": 'Convite para o projeto "{project}" no RevisaMeta',
        "email.invite.body": (
            'Olá!\n\n{inviter} convidou você para participar do projeto "{project}".\n'
            "Para aceitar, abra o link abaixo:\n{link}\n\nO convite vale por {days} dias."
        ),
    },
    "en": {
        "error.internal": "Something went wrong. Please try again in a moment.",
        "error.validation": "Some fields are invalid. Please check the data you sent.",
        "error.not_found": "This item does not exist or you do not have access to it.",
        "error.not_authenticated": "Please sign in to continue.",
        "error.forbidden": "You do not have permission to do this in this project.",
        "error.version_conflict": (
            "Someone else changed this item while you were editing. "
            "Reload to see the latest version."
        ),
        "error.rate_limited": "Too many attempts. Please wait a moment and try again.",
        "error.stats_failed": "The statistics service could not produce the result.",
        "error.stats_unavailable": (
            "The statistics service is unavailable right now. Nothing was saved. "
            "Please try again in a few minutes."
        ),
        "auth.email_taken": "An account with this e-mail already exists.",
        "auth.invalid_credentials": "Incorrect e-mail or password.",
        "auth.email_not_verified": (
            "Please confirm your e-mail before signing in. Check your inbox."
        ),
        "auth.account_disabled": "This account is disabled.",
        "auth.weak_password": (
            "The password must have at least 10 characters, with letters and numbers."
        ),
        "auth.captcha_failed": "We could not confirm you are not a robot. Please try again.",
        "auth.terms_required": "You must accept the terms of use and the privacy policy.",
        "auth.invalid_token": "This link is invalid or has expired.",
        "auth.session_expired": "Your session has expired. Please sign in again.",
        "project.creator_cannot_be_removed": (
            "The project creator cannot be removed before transferring administration."
        ),
        "project.last_admin": "The project must have at least one administrator.",
        "project.already_member": "This person is already a project member.",
        "protocol.duplicate_name": "An item with this name already exists in the project protocol.",
        "study.duplicate_label": "A study with this name already exists in the project.",
        "pdf.upload_not_ready": "This PDF upload has not finished yet. Wait for processing and try again.",
        "extraction.not_editable": "This extraction has been submitted and can no longer be changed.",
        "extraction.impossible.n_not_positive": "The n (or the total) must be greater than zero.",
        "extraction.impossible.sd_not_positive": "The SD must be greater than zero.",
        "extraction.impossible.se_not_positive": "The SE must be greater than zero.",
        "extraction.impossible.negative_events": "The number of events cannot be negative.",
        "extraction.impossible.events_gt_total": "The number of events cannot exceed the group total.",
        "extraction.impossible.ci_inverted": "The lower CI limit cannot be greater than the upper limit.",
        "extraction.impossible.iqr_inverted": "The 1st quartile cannot be greater than the 3rd.",
        "extraction.impossible.range_inverted": "The minimum cannot be greater than the maximum.",
        "extraction.impossible.median_outside": "The median must lie between the quartiles (or between the minimum and maximum).",
        "extraction.alert_resolved": "This alert has already been resolved by correcting the value.",
        "extraction.alert_confirm_direction": (
            "This alert is resolved by confirming the effect direction sentence."
        ),
        "extraction.impossible.ratio_not_positive": "OR, RR and HR are always above zero (estimate and CI). Check the value typed.",
        "extraction.impossible.p_out_of_range": "The p value must be between 0 and 1.",
        "rob.tool_in_use": "This instrument already has assessments; its structure can no longer change.",
        "rob.study_has_assessments": "This study already has assessments with another instrument, which can no longer be changed.",
        "rob.has_official_rule": "This instrument has an official rule for the overall judgement.",
        "rob.invalid_rule": "The group rule has an error: check its levels, answers and questions.",
        "rob.no_tool_confirmed": "The admin has not confirmed the instrument of this study yet.",
        "rob.result_required": "This instrument assesses each result: choose the outcome and time point.",
        "rob.unknown_result": "This outcome or time point is not in the protocol.",
        "rob.enough_reviewers": "This study already has {limit} individual assessments for this result.",
        "rob.not_editable": "This assessment has been submitted and can no longer change.",
        "rob.invalid_answer": "Invalid answer for question {key}.",
        "rob.wrong_target": "Question {key} is answered at another level (study, outcome or result).",
        "rob.unknown_annotation": "This passage is not from a PDF of this study.",
        "rob.unknown_variant": "Invalid variant for domain {key}.",
        "rob.no_domain_judgement": "This instrument has no domain judgements, only the overall one.",
        "rob.unknown_domain": "Domain {key} does not exist in this instrument.",
        "rob.invalid_judgement": "Invalid judgement for this instrument.",
        "rob.invalid_direction": "Invalid direction of bias for this instrument.",
        "rob.consensus_waiting": "The consensus can only be created after both individual assessments are submitted.",
        "rob.consensus_exists": "This assessment already has a consensus.",
        "rob.not_a_conflict": "This item is not a conflict between the two reviewers.",
        "rob.reason_required": "Briefly explain why the consensus differs from both reviewers.",
        "rob.undecided_conflicts": "There are still {count} undecided conflict(s). Decide all of them before submitting the consensus.",
        "rob.nothing_to_plot": "No study has a submitted consensus for this instrument and result; there is nothing to draw.",
        "rob.plot_missing_studies": "{count} study(ies) without a submitted consensus would be left out of the plot. Confirm to draw it anyway.",
        "rob.no_robvis_template": "robvis has no template for this instrument; use CSV, XLSX or DOCX.",
        "rob.nothing_to_export": "No study has a submitted consensus for this instrument and result; there is nothing to export.",
        "rob.export_missing_studies": "{count} study(ies) without a submitted consensus would be left out of the file. Confirm to export anyway.",
        "rob_import.invalid_mapping": "Check the column mapping: study, overall judgement and (except for checklists) every domain are required.",
        "rob.review_not_ready": "The stage can only be locked when every study is finished ({ready} of {total}).",
        "rob.reopen_only_consensus": "Only a consensus can be reopened. To fix an import, discard it and import it again.",
        "rob.not_submitted": "This assessment is not submitted.",
        "rob.discard_only_import": "Only an imported assessment can be discarded.",
        "plan.unknown_group": "The chosen group does not exist in the protocol.",
        "plan.unknown_outcome": "The chosen outcome does not exist in the protocol.",
        "plan.measure_mismatch": 'The effect measure does not match the type of the outcome "{outcome}".',
        "plan.unknown_timepoint": 'The chosen time point does not exist in the outcome "{outcome}".',
        "analysis.unknown_result": "This outcome does not have the chosen time point.",
        "analysis.measure_mismatch": "The effect measure does not match the type of the outcome.",
        "analysis.blocked": "The analysis cannot run: {blocks}. See the reasons in step 1.",
        "rob.incomplete": "There are still {count} item(s) to complete before submitting.",
        "rob.unknown_template": "This instrument is not in the catalog.",
        "rob.already_enabled": "This instrument, in this version, is already enabled in the project.",
        "rob.unknown_question": 'Question "{key}" does not exist in this instrument.',
        "rob.text_too_long": 'The text of question "{key}" is too long.',
        "rob.not_generic": "Only the generic instrument has domains defined by the group.",
        "export.empty": "There is no data to export: no study has a submitted consensus. Use the individual (pre-consensus) option if needed.",
        "export.incomplete": "{count} study(ies) would be left out of the file. Check the list and confirm the export.",
        "stage.locked": "This stage is locked. Ask the admin to unlock it (with a justification) if something must change.",
        "stage.not_locked": "This stage is not locked.",
        "review.not_ready": "The stage can only be locked when every study has a submitted consensus and no open alert ({ready} of {total} ready).",
        "review.not_a_consensus": "Consensus not found.",
        "review.not_submitted": "Only a submitted consensus can be reopened.",
        "consensus.exists": "This study already has a consensus.",
        "consensus.waiting_extractions": "The consensus can only be created after {needed} individual extraction(s) are submitted.",
        "consensus.missing": "Create the consensus before deciding the divergences.",
        "consensus.not_double": "This study does not have two extractions to compare.",
        "consensus.not_a_divergence": "This field is not a divergence between the two extractors.",
        "consensus.reason_required": "Briefly explain why the consensus value differs from both extractors.",
        "consensus.undecided_divergences": "There are still {count} undecided divergence(s). Decide all of them before submitting the consensus.",
        "extraction.open_blocking_alerts": "Some alerts prevent submission. Fix the values or justify the alerts before submitting.",
        "extraction.enough_extractors": "This study already has {limit} extractor(s). Ask the admin to adjust it if needed.",
        "extraction.invalid_field": 'The field "{field}" has an invalid value.',
        "extraction.unknown_group": "This comparison group does not exist in the project protocol.",
        "extraction.arm_in_use": "This group has outcome numbers recorded. Delete them before removing the group.",
        "extraction.unknown_outcome": "This outcome does not exist in the project protocol.",
        "extraction.invalid_scale_range": "The scale minimum must be lower than the maximum.",
        "extraction.unknown_annotation": "The chosen passage is not from a PDF of this study.",
        "extraction.unknown_arm": "This group does not belong to this extraction.",
        "extraction.unknown_timepoint": "This time point is not in the outcome protocol.",
        "study.duplicate_doi": "An article with this DOI already exists in the project.",
        "study.last_report": "A study needs at least one article. To remove it from the review, delete the study.",
        "import.too_large": "The file exceeds the {limit} MB limit.",
        "import.unsupported_format": "Format not accepted. Send an .xlsx spreadsheet or a .csv file.",
        "import.empty_file": "The file is empty or has no header row.",
        "import.invalid_mapping": "Check the column mapping: the title is required.",
        "import.too_many_rows": "The file exceeds the {limit} row limit.",
        "invitation.expired": "This invitation has expired. Ask the project admin for a new one.",
        "invitation.already_accepted": "This invitation has already been used.",
        "invitation.wrong_email": "This invitation was sent to a different e-mail.",
        "quota.projects_exceeded": (
            "You have reached the limit of {limit} projects. "
            "Archive a project or ask the system administrator for more space."
        ),
        "quota.storage_exceeded": (
            "You have reached your storage limit ({limit} MB). "
            "Remove files or ask the system administrator for more space."
        ),
        "upload.too_large": "The file exceeds the {limit} MB limit.",
        "upload.not_pdf": "Only PDF files are accepted.",
        "upload.incomplete": "Some parts of the file are still missing. Continue the upload.",
        "upload.expired": "This upload has expired. Please start again.",
        "email.verify.subject": "Confirm your e-mail on RevisaMeta",
        "email.verify.body": (
            "Hello, {name}!\n\nTo confirm your e-mail, open the link below:\n{link}\n\n"
            "The link is valid for 48 hours. "
            "If you did not create this account, ignore this message."
        ),
        "email.invite.subject": 'Invitation to the project "{project}" on RevisaMeta',
        "email.invite.body": (
            'Hello!\n\n{inviter} invited you to join the project "{project}".\n'
            "To accept, open the link below:\n{link}\n\nThe invitation is valid for {days} days."
        ),
    },
}


def negotiate_language(accept_language: str | None) -> Language:
    """Pick the best supported language from an Accept-Language header."""
    if not accept_language:
        return DEFAULT_LANGUAGE
    for part in accept_language.split(","):
        tag = part.split(";")[0].strip().lower()
        if tag.startswith("pt"):
            return "pt-BR"
        if tag.startswith("en"):
            return "en"
    return DEFAULT_LANGUAGE


def translate(code: str, language: Language = DEFAULT_LANGUAGE, **params: object) -> str:
    template = MESSAGES[language].get(code) or MESSAGES[DEFAULT_LANGUAGE].get(code) or code
    return template.format(**params) if params else template
