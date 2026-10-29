from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Task(models.Model):
    class Priority(models.IntegerChoices):
        # Stored as integers so ordering by priority is low < medium < high
        # (a CharField would sort alphabetically: high, low, medium).
        LOW = 1, 'Low'
        MEDIUM = 2, 'Medium'
        HIGH = 3, 'High'

    # Link the task to Django's built-in User model. Each task belongs
    # to exactly one user; if that user is deleted, their tasks go too.
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(choices=Priority.choices, default=Priority.MEDIUM)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        """Not done and due before today (in the project's time zone)."""
        return (
            not self.completed
            and self.due_date is not None
            and self.due_date < timezone.localdate()
        )
