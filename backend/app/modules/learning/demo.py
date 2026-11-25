"""Demonstration project with a public dataset (docs/modulos.md 7.11).

Nine studies of `dat.normand1999` (metafor/metadat): stroke rehabilitation, length of
hospital stay in specialist care versus routine care. Clinical data are never invented
(rule 0.1.6): the numbers come from demo_normand1999.json, a copy of what metafor wrote
in stats-r/fixtures (a test checks the copy). Every study gets a submitted consensus so
the meta-analysis wizard can be used right away. Length of stay is "lower is better", so
the demo also shows the sign inversion.
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_id
from app.modules.auth.models import User
from app.modules.extraction.models import (
    Extraction,
    ExtractionForm,
    OutcomeData,
    OutcomeMeasure,
    StudyArm,
)
from app.modules.extraction.schemas import DEFAULT_FORM
from app.modules.projects.models import Project, ProjectMember
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.quotas.service import ensure_can_create_project
from app.modules.studies.models import Study

DATA_FILE = Path(__file__).with_name("demo_normand1999.json")
Lang = Literal["pt-BR", "en"]

TEXTS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "title": "Demonstração: reabilitação após AVC (dat.normand1999, dados públicos)",
        "question": (
            "Pacientes com AVC tratados em unidade especializada tiveram menor tempo de "
            "internação do que os tratados em cuidado habitual? (dados públicos do pacote "
            "metafor, para demonstração)"
        ),
        "outcome": "Tempo de internação (dias)",
        "timepoint": "alta",
        "special": "Unidade especializada",
        "routine": "Cuidado habitual",
        "scale": "Dias de internação",
        "notes": "Projeto de demonstração com dados públicos (metafor::dat.normand1999).",
        "source": "metafor::dat.normand1999 (dados públicos)",
    },
    "en": {
        "title": "Demonstration: stroke rehabilitation (dat.normand1999, public data)",
        "question": (
            "Did stroke patients treated in a specialist unit have a shorter hospital stay "
            "than those in routine care? (public data from the metafor package, for "
            "demonstration)"
        ),
        "outcome": "Length of hospital stay (days)",
        "timepoint": "discharge",
        "special": "Specialist unit",
        "routine": "Routine care",
        "scale": "Days in hospital",
        "notes": "Demonstration project with public data (metafor::dat.normand1999).",
        "source": "metafor::dat.normand1999 (public data)",
    },
}


def normand() -> dict[str, list[object]]:
    data: dict[str, list[object]] = json.loads(DATA_FILE.read_text(encoding="utf-8"))["data"]
    return data


async def create_demo(session: AsyncSession, user: User, lang: Lang = "pt-BR") -> uuid.UUID:
    """Creates the demonstration project for `user` (who becomes its admin) and commits."""
    await ensure_can_create_project(session, user.id)
    t = TEXTS[lang]
    data = normand()
    project = Project(
        id=new_id(),
        title=t["title"],
        question=t["question"],
        owner_id=user.id,
        created_by=user.id,
        report_language=lang,
        double_extraction=True,
    )
    session.add(project)
    await session.flush()
    session.add(
        ProjectMember(project_id=project.id, user_id=user.id, roles=["admin"], created_by=user.id)
    )
    outcome = Outcome(
        project_id=project.id,
        created_by=user.id,
        name=t["outcome"],
        type="continuous",
        higher_is_better=False,
        is_primary=True,
        timepoints=[t["timepoint"]],
    )
    special = ComparisonGroup(
        project_id=project.id, created_by=user.id, label=t["special"], position=0
    )
    routine = ComparisonGroup(
        project_id=project.id, created_by=user.id, label=t["routine"], position=1
    )
    session.add_all([outcome, special, routine])
    await session.flush()
    project.analysis_plan = {
        "comparison": {"group1_id": str(special.id), "group2_id": str(routine.id)},
        "outcomes": [{"outcome_id": str(outcome.id), "measure": "MD", "timepoint": t["timepoint"]}],
        "notes": t["notes"],
    }
    form = ExtractionForm(
        id=new_id(),
        project_id=project.id,
        created_by=user.id,
        form_version=1,
        schema=DEFAULT_FORM.model_dump(),
        is_current=True,
    )
    session.add(form)
    await session.flush()
    now = datetime.now(UTC)
    for i, label in enumerate(data["label"]):
        study = Study(project_id=project.id, created_by=user.id, label=str(label), design="rct")
        session.add(study)
        await session.flush()
        extraction = Extraction(
            project_id=project.id,
            created_by=user.id,
            study_id=study.id,
            form_id=form.id,
            kind="consensus",
            status="submitted",
            characteristics={},
            submitted_by=user.id,
            submitted_at=now,
        )
        session.add(extraction)
        await session.flush()
        session.add(
            OutcomeMeasure(
                project_id=project.id,
                created_by=user.id,
                extraction_id=extraction.id,
                outcome_id=outcome.id,
                scale_name=t["scale"],
                higher_is_better=False,
            )
        )
        for position, (group, suffix) in enumerate(((special, "1"), (routine, "2"))):
            n = int(str(data[f"n{suffix}i"][i]))
            arm = StudyArm(
                project_id=project.id,
                created_by=user.id,
                extraction_id=extraction.id,
                label=group.label,
                n=n,
                mapped_group_id=group.id,
                position=position,
            )
            session.add(arm)
            await session.flush()
            session.add(
                OutcomeData(
                    project_id=project.id,
                    created_by=user.id,
                    extraction_id=extraction.id,
                    arm_id=arm.id,
                    outcome_id=outcome.id,
                    timepoint=t["timepoint"],
                    n=n,
                    mean=Decimal(str(data[f"m{suffix}i"][i])),
                    sd=Decimal(str(data[f"sd{suffix}i"][i])),
                    dispersion_type="sd",
                    source_location=t["source"],
                    direction_confirmed=True,
                )
            )
    await session.commit()
    return project.id
