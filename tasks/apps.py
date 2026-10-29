from django.apps import AppConfig


class TasksConfig(AppConfig):
    name = 'tasks'

    def ready(self):
        from . import checks  # noqa: F401  (registers the system checks)
