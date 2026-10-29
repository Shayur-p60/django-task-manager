from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.utils import timezone

from .models import Task


def _attempts_cache_key(username: str) -> str:
    return f"login_attempts:{username.strip().lower()}"


class ThrottledAuthenticationForm(AuthenticationForm):
    """
    Drop-in replacement for Django's AuthenticationForm that adds basic
    login-attempt throttling: after LOGIN_THROTTLE_MAX_ATTEMPTS failed
    logins for a given username, further attempts are blocked for
    LOGIN_THROTTLE_LOCKOUT_SECONDS, regardless of whether the password
    given is actually correct.

    This uses Django's cache framework (LocMemCache by default — no
    extra service required) as the attempt counter, keyed by username.
    Successful login clears the counter.

    Note: this throttles by *username*, not by IP, which is the simpler
    of the two common approaches and is enough to stop naive credential
    stuffing against a single account. A production system fronting
    sensitive data would typically combine this with IP-based throttling
    (e.g. at a reverse proxy / WAF layer) as well.
    """

    def clean(self):
        username = self.cleaned_data.get('username')

        if username:
            key = _attempts_cache_key(username)
            attempts = cache.get(key, 0)
            max_attempts = getattr(settings, 'LOGIN_THROTTLE_MAX_ATTEMPTS', 5)

            if attempts >= max_attempts:
                lockout_minutes = getattr(settings, 'LOGIN_THROTTLE_LOCKOUT_SECONDS', 900) // 60
                raise forms.ValidationError(
                    "Too many failed login attempts for this account. "
                    "Please try again in about %(minutes)d minutes.",
                    code='too_many_attempts',
                    params={'minutes': lockout_minutes},
                )

        try:
            cleaned_data = super().clean()
        except forms.ValidationError:
            # A failed attempt (bad username/password) — increment the counter.
            if username:
                key = _attempts_cache_key(username)
                lockout_seconds = getattr(settings, 'LOGIN_THROTTLE_LOCKOUT_SECONDS', 900)
                cache.set(key, cache.get(key, 0) + 1, lockout_seconds)
            raise

        # Successful login — clear any prior failed-attempt count.
        if username:
            cache.delete(_attempts_cache_key(username))

        return cleaned_data


class TaskForm(forms.ModelForm):
    """
    Create/edit form for a task. The "completed" checkbox only appears when
    editing an existing task; new tasks always start as not completed.
    """

    class Meta:
        model = Task
        fields = ['title', 'description', 'due_date', 'priority', 'completed']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Add a new task...'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Details (optional)'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }
        error_messages = {
            'title': {'required': 'Task title cannot be empty.'},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_new:
            del self.fields['completed']
        # Priority falls back to the model default (medium) when not sent.
        self.fields['priority'].required = False

    @property
    def is_new(self):
        return self.instance.pk is None

    def clean_priority(self):
        return self.cleaned_data.get('priority') or Task.Priority.MEDIUM

    def clean_due_date(self):
        due_date = self.cleaned_data.get('due_date')
        # Only block past dates on create, so an existing overdue task can
        # still be edited without having to change its due date.
        if self.is_new and due_date and due_date < timezone.localdate():
            raise forms.ValidationError('Due date cannot be in the past.', code='past_due_date')
        return due_date
