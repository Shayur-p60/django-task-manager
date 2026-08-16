from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from .models import Task


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


@login_required
def dashboard(request):
    """Standard dashboard: users only see and manage their own tasks."""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            title = request.POST.get('title', '').strip()
            if title:
                Task.objects.create(user=request.user, title=title)
                messages.success(request, f"Added task: '{title}'")
            else:
                messages.error(request, 'Task title cannot be empty.')

        elif action == 'toggle':
            task = get_object_or_404(Task, pk=request.POST.get('task_id'), user=request.user)
            task.completed = not task.completed
            task.save()

        elif action == 'delete':
            task = get_object_or_404(Task, pk=request.POST.get('task_id'), user=request.user)
            task.delete()
            messages.success(request, 'Task deleted.')

        return redirect('dashboard')

    tasks = Task.objects.filter(user=request.user)
    return render(request, 'tasks/dashboard.html', {'tasks': tasks})


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
