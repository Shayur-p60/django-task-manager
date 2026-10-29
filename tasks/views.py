from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import TaskForm
from .models import Task

TASKS_PER_PAGE = 10

STATUS_CHOICES = [('all', 'All'), ('active', 'Active'), ('completed', 'Completed')]
SORT_CHOICES = [('newest', 'Newest'), ('due', 'Due date'), ('priority', 'Priority')]

# Tasks without a due date go last when sorting by due date.
SORT_ORDERING = {
    'newest': ['-created_at'],
    'due': [F('due_date').asc(nulls_last=True), '-priority', '-created_at'],
    'priority': ['-priority', F('due_date').asc(nulls_last=True), '-created_at'],
}


@require_http_methods(['GET', 'HEAD'])
def healthz(request):
    """Health check for Docker and hosting platforms: app is up and the DB answers."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        return JsonResponse({'status': 'error', 'database': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})


def register(request):
    """Handles user registration and securely hashes the password."""
    if request.method == 'POST':
        # UserCreationForm automatically handles secure password hashing (PBKDF2)
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created! You can now log in.')
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def _safe_next_url(request):
    """
    The "next" URL from the request (POST, then GET) if it points back at
    this site, otherwise the dashboard. Checked with
    url_has_allowed_host_and_scheme so it can't be used as an open redirect.
    """
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return reverse('dashboard')


def _get_user_task(request, pk):
    # Scoping by user means another user's task is a 404, not a 403,
    # so we don't reveal which task IDs exist.
    return get_object_or_404(Task, pk=pk, user=request.user)


@login_required
@require_http_methods(['GET', 'HEAD'])
def dashboard(request):
    """Standard dashboard: users only see their own tasks."""
    user_tasks = Task.objects.filter(user=request.user)
    tasks = user_tasks

    status = request.GET.get('status', 'all')
    if status == 'active':
        tasks = tasks.filter(completed=False)
    elif status == 'completed':
        tasks = tasks.filter(completed=True)
    else:
        status = 'all'

    priority = request.GET.get('priority', '')
    if priority in {str(value) for value in Task.Priority.values}:
        tasks = tasks.filter(priority=int(priority))
    else:
        priority = ''

    query = request.GET.get('q', '').strip()
    if query:
        tasks = tasks.filter(title__icontains=query)

    sort = request.GET.get('sort', 'newest')
    if sort not in SORT_ORDERING:
        sort = 'newest'
    tasks = tasks.order_by(*SORT_ORDERING[sort])

    page_obj = Paginator(tasks, TASKS_PER_PAGE).get_page(request.GET.get('page'))

    # Current filters without the page number, for the pagination links.
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'tasks/dashboard.html', {
        'form': TaskForm(),
        'page_obj': page_obj,
        'tasks': page_obj.object_list,
        'has_any_tasks': user_tasks.exists(),
        'filters': {'status': status, 'priority': priority, 'q': query, 'sort': sort},
        'status_choices': STATUS_CHOICES,
        'sort_choices': SORT_CHOICES,
        'priority_choices': Task.Priority.choices,
        'querystring': params.urlencode(),
        'current_url': request.get_full_path(),
    })


@login_required
@require_POST
def task_create(request):
    form = TaskForm(request.POST)
    if form.is_valid():
        task = form.save(commit=False)
        task.user = request.user
        task.save()
        messages.success(request, f"Added task: '{task.title}'")
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect(_safe_next_url(request))


@login_required
@require_http_methods(['GET', 'HEAD', 'POST'])
def task_update(request, pk):
    task = _get_user_task(request, pk)
    form = TaskForm(request.POST or None, instance=task)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f"Updated task: '{task.title}'")
        return redirect(_safe_next_url(request))
    return render(request, 'tasks/task_form.html', {
        'form': form,
        'task': task,
        'next': _safe_next_url(request),
    })


@login_required
@require_POST
def task_toggle(request, pk):
    task = _get_user_task(request, pk)
    task.completed = not task.completed
    task.save(update_fields=['completed', 'updated_at'])
    return redirect(_safe_next_url(request))


@login_required
@require_POST
def task_delete(request, pk):
    task = _get_user_task(request, pk)
    task.delete()
    messages.success(request, 'Task deleted.')
    return redirect(_safe_next_url(request))


# --- USER ROLES & PERMISSIONS ---

@login_required
def admin_dashboard(request):
    """
    Admin dashboard: can see every user's tasks, not just their own.

    @login_required alone would only catch users who aren't signed in at
    all (redirecting them to the login page). A signed-in user who just
    isn't staff is a *different* case — they're logged in, they simply
    don't have permission — so that gets a proper 403 Forbidden instead
    of being redirected back to login (which would look like they'd been
    logged out).
    """
    if not request.user.is_staff:
        raise PermissionDenied("You need admin (staff) access to view this page.")

    all_tasks = Task.objects.select_related('user').all()
    return render(request, 'tasks/admin_dashboard.html', {'tasks': all_tasks})
