# ruff: noqa: E501  (legal-style text reads better one sentence per line)
"""Data-use notice the project admin must accept before the AI is turned on (docs/ia.md
7.15.5). Versioned: changing the text means a new version, and projects that accepted
an older one must accept again. Facts about the Gemini free tier checked on 2026-11-23
(docs/roteiro.md, stage 7)."""

VERSION = "2026-11-23"

NOTICE: dict[str, dict[str, object]] = {
    "pt-BR": {
        "title": "Aviso de uso de dados da IA",
        "paragraphs": [
            "A IA é opcional e fica desligada até um administrador aceitar este aviso. Ela só explica e aponta trechos: não calcula estatística, não decide inclusão nem risco de viés, e nenhuma sugestão vira dado sem confirmação de uma pessoa.",
            "Provedor: Google (API Gemini, plano gratuito). No plano gratuito, o Google pode usar o que é enviado e as respostas para melhorar os produtos dele, e pessoas podem revisar esse conteúdo. Não use a IA se o projeto não puder aceitar isso.",
            "O que é enviado, só quando alguém usa uma função: trechos de artigos publicados que a pessoa pediu para consultar e resultados já calculados que a pessoa pediu para explicar. Só o trecho necessário, nunca o projeto inteiro.",
            "O que nunca é enviado: anotações privadas, comentários, nomes ou e-mails de membros, decisões de triagem, extrações e avaliações em andamento, nem PDFs inteiros.",
            "Cada pessoa tem uma cota diária de uso. Quando a cota gratuita acaba, a IA fica indisponível até renovar; o resto do sistema continua funcionando.",
            "O aceite fica registrado na auditoria (quem, quando e qual versão deste aviso). Um administrador pode desligar a IA a qualquer momento.",
        ],
        "accept": "Li e aceito este aviso para este projeto.",
    },
    "en": {
        "title": "AI data-use notice",
        "paragraphs": [
            "The AI is optional and stays off until an admin accepts this notice. It only explains and points at passages: it does not compute statistics, does not decide inclusion or risk of bias, and no suggestion becomes data without a person's confirmation.",
            "Provider: Google (Gemini API, free tier). On the free tier, Google may use what is sent and the answers to improve its products, and people may review that content. Do not use the AI if the project cannot accept this.",
            "What is sent, only when someone uses a feature: passages of published articles the person asked to look into and already computed results the person asked to explain. Only the passage needed, never the whole project.",
            "What is never sent: private notes, comments, names or e-mails of members, screening decisions, extractions and assessments in progress, or whole PDFs.",
            "Each person has a daily usage quota. When the free quota runs out, the AI is unavailable until it renews; the rest of the system keeps working.",
            "The acceptance is recorded in the audit log (who, when and which version of this notice). An admin can turn the AI off at any time.",
        ],
        "accept": "I have read and accept this notice for this project.",
    },
}
