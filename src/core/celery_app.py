import os

from celery import Celery

celery_app = Celery(
    "meeting_assistant",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)

# Modules whose `tasks.py` the worker registers. Listed explicitly so a module
# is never skipped silently; modules without a `tasks.py` are ignored.
INSTALLED_MODULES = [
    "src.modules.auth",
    "src.modules.inference",
    "src.modules.meetings",
    "src.modules.settings",
    "src.modules.uploads",
]

celery_app.autodiscover_tasks(packages=INSTALLED_MODULES, related_name="tasks")
