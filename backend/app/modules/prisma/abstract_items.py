"""PRISMA 2020 for Abstracts structure (Page et al., BMJ 2021;372:n71; CC BY 4.0).

Item numbers, sections and topics only, with a short summary written for this system
(pt and en); the official wording is linked, not reproduced (as in checklist_items).
Codes use the prefix "A" so they live next to the PRISMA 2020 items.
"""

from app.modules.prisma.checklist_items import Item, _i

SOURCE = "https://www.prisma-statement.org/prisma-2020-for-abstracts"

ITEMS: list[Item] = [
    _i(
        "A1",
        "title",
        "Título",
        "Title",
        "Diz que é uma revisão sistemática.",
        "Says it is a systematic review.",
    ),
    _i(
        "A2",
        "background",
        "Objetivos",
        "Objectives",
        "Objetivo ou pergunta principal da revisão.",
        "Main objective or question of the review.",
        "question",
    ),
    _i(
        "A3",
        "methods",
        "Critérios de elegibilidade",
        "Eligibility criteria",
        "Critérios de inclusão e exclusão.",
        "Inclusion and exclusion criteria.",
    ),
    _i(
        "A4",
        "methods",
        "Fontes de informação",
        "Information sources",
        "Bases e fontes consultadas, com a data da última busca.",
        "Databases and sources searched, with the date last searched.",
        "searches",
    ),
    _i(
        "A5",
        "methods",
        "Risco de viés",
        "Risk of bias",
        "Métodos usados para avaliar o risco de viés.",
        "Methods used to assess risk of bias.",
        "risk_of_bias",
    ),
    _i(
        "A6",
        "methods",
        "Síntese dos resultados",
        "Synthesis of results",
        "Métodos usados para apresentar e sintetizar os resultados.",
        "Methods used to present and synthesise results.",
        "analyses",
    ),
    _i(
        "A7",
        "results",
        "Estudos incluídos",
        "Included studies",
        "Número de estudos e participantes, e suas características principais.",
        "Number of studies and participants, and their main characteristics.",
        "studies",
    ),
    _i(
        "A8",
        "results",
        "Síntese dos resultados",
        "Synthesis of results",
        "Resultados dos desfechos principais, de preferência com efeito e IC.",
        "Results of the main outcomes, ideally with effect and CI.",
        "analyses",
    ),
    _i(
        "A9",
        "discussion",
        "Limitações da evidência",
        "Limitations of evidence",
        "Resumo das limitações da evidência (risco de viés, inconsistência, imprecisão).",
        "Summary of the limitations of the evidence (risk of bias, inconsistency, imprecision).",
    ),
    _i(
        "A10",
        "discussion",
        "Interpretação",
        "Interpretation",
        "Interpretação geral dos resultados e implicações.",
        "General interpretation of the results and implications.",
    ),
    _i(
        "A11",
        "other",
        "Financiamento",
        "Funding",
        "Fonte principal de financiamento.",
        "Main source of funding.",
    ),
    _i(
        "A12",
        "other",
        "Registro",
        "Registration",
        "Nome do registro e número.",
        "Register name and number.",
        "prospero",
    ),
]
CODES = [item["code"] for item in ITEMS]
