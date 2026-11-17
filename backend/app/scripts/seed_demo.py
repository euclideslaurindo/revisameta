"""Demonstration project with a public dataset (docs/modulos.md 7.11; `make seed-demo`).

Creates, for an existing user, a project marked as a demonstration with the nine
studies of `dat.normand1999` (metafor/metadat): stroke rehabilitation, length of
hospital stay in specialist care versus routine care. Clinical data are never
invented (rule 0.1.6): the numbers are read from stats-r/fixtures/meta-analysis.json,
which metafor wrote, and every study gets a submitted consensus so the meta-analysis
wizard can be used right away.

Length of stay is "lower is better", so the demo also shows the sign inversion.

Usage (inside the backend container, with the fixtures mounted at /stats-fixtures):
    python -m app.scripts.seed_demo --email someone@example.org
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

import app.db.models  # noqa: F401 - registers every table for the foreign keys
from app.db.base import new_id
from app.db.session import get_sessionmaker
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
from app.modules.studies.models import Study

TITLE = "Demonstração: reabilitação após AVC (dat.normand1999, dados públicos)"
FIXTURE_NAMES = ("/stats-fixtures/meta-analysis.json", "../stats-r/fixtures/meta-analysis.json")


def _normand() -> dict[str, list[object]]:
    for name in FIXTURE_NAMES:
        path = Path(name)
        if path.exists():
            cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
            case = next(c for c in cases if c["name"] == "dat.normand1999_MD_REML_knha")
            data: dict[str, list[object]] = case["request"]["data"]
            return data
    raise SystemExit(
        "meta-analysis.json fixture not found (mount stats-r/fixtures at /stats-fixtures)"
    )


async def seed(email: str) -> str:
    data = _normand()
    async with get_sessionmaker()() as session:
        user = (await session.scalars(select(User).where(User.email == email))).first()
        if user is None:
            raise SystemExit(f"no user with e-mail {email}")
        project = Project(
            id=new_id(),
            title=TITLE,
            question=(
                "Pacientes com AVC tratados em unidade especializada tiveram menor tempo de "
                "internação do que os tratados em cuidado habitual? (dados públicos do "
                "pacote metafor, para demonstração)"
            ),
            owner_id=user.id,
            created_by=user.id,
            double_extraction=True,
        )
        session.add(project)
        await session.flush()
        session.add(
            ProjectMember(
                project_id=project.id, user_id=user.id, roles=["admin"], created_by=user.id
            )
        )
        outcome = Outcome(
            project_id=project.id,
            created_by=user.id,
            name="Tempo de internação (dias)",
            type="continuous",
            higher_is_better=False,
            is_primary=True,
            timepoints=["alta"],
        )
        special = ComparisonGroup(
            project_id=project.id, created_by=user.id, label="Unidade especializada", position=0
        )
        routine = ComparisonGroup(
            project_id=project.id, created_by=user.id, label="Cuidado habitual", position=1
        )
        session.add_all([outcome, special, routine])
        await session.flush()
        project.analysis_plan = {
            "comparison": {"group1_id": str(special.id), "group2_id": str(routine.id)},
            "outcomes": [{"outcome_id": str(outcome.id), "measure": "MD", "timepoint": "alta"}],
            "notes": "Projeto de demonstração com dados públicos (metafor::dat.normand1999).",
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
                    scale_name="Dias de internação",
                    higher_is_better=False,
                )
            )
            for position, (group, suffix) in enumerate(((special, "1"), (routine, "2"))):
                arm = StudyArm(
                    project_id=project.id,
                    created_by=user.id,
                    extraction_id=extraction.id,
                    label=group.label,
                    n=int(str(data[f"n{suffix}i"][i])),
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
                        timepoint="alta",
                        n=int(str(data[f"n{suffix}i"][i])),
                        mean=Decimal(str(data[f"m{suffix}i"][i])),
                        sd=Decimal(str(data[f"sd{suffix}i"][i])),
                        dispersion_type="sd",
                        source_location="metafor::dat.normand1999 (dados públicos)",
                        direction_confirmed=True,
                    )
                )
        await session.commit()
        return str(project.id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="existing user who will own the project")
    args = parser.parse_args()
    project_id = asyncio.run(seed(args.email))
    print(f"Demo project created: {project_id}")


if __name__ == "__main__":
    main()
