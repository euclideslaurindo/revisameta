from app.modules.jobs.models import BackgroundJob
from app.modules.uploads.schemas import JobOut


def job_out(job: BackgroundJob) -> JobOut:
    return JobOut.model_validate(job)
