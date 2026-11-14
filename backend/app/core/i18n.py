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
