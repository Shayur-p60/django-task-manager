from django.db import models
from django.contrib.auth.models import User


class Task(models.Model):
    # Link the task to Django's built-in User model. Each task belongs
    # to exactly one user; if that user is deleted, their tasks go too.
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=200)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
