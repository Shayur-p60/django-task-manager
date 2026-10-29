"""
Test suite for the tasks app: registration, authentication (including
login throttling), task CRUD, role-based permissions, and password reset.

Run with: pytest
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from .models import Task


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username='alice', email='alice@example.com', password='TestPass123!'
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username='admin_bob', email='bob@example.com', password='TestPass123!', is_staff=True
    )


@pytest.fixture
def logged_in_client(client, regular_user):
    client.login(username='alice', password='TestPass123!')
    return client


@pytest.fixture
def logged_in_staff_client(client, staff_user):
    client.login(username='admin_bob', password='TestPass123!')
    return client


# --- Registration ---

@pytest.mark.django_db
def test_register_creates_user_with_hashed_password(client):
    response = client.post(reverse('register'), {
        'username': 'charlie',
        'password1': 'SecurePass789!',
        'password2': 'SecurePass789!',
    })
    assert response.status_code == 302  # redirects to login on success

    user = User.objects.get(username='charlie')
    assert user.password.startswith('pbkdf2_')  # hashed, not plaintext
    assert user.check_password('SecurePass789!')


@pytest.mark.django_db
def test_register_rejects_mismatched_passwords(client):
    response = client.post(reverse('register'), {
        'username': 'charlie',
        'password1': 'SecurePass789!',
        'password2': 'DifferentPass!',
    })
    assert response.status_code == 200  # re-renders form with errors
    assert not User.objects.filter(username='charlie').exists()


# --- Login ---

@pytest.mark.django_db
def test_login_success_redirects_to_dashboard(client, regular_user):
    response = client.post(reverse('login'), {
        'username': 'alice', 'password': 'TestPass123!',
    })
    assert response.status_code == 302
    assert response.url == reverse('dashboard')


@pytest.mark.django_db
def test_login_wrong_password_fails(client, regular_user):
    response = client.post(reverse('login'), {
        'username': 'alice', 'password': 'WrongPassword',
    })
    assert response.status_code == 200  # re-renders login form
    assert not response.wsgi_request.user.is_authenticated


# --- Login throttling ---

@pytest.mark.django_db
def test_login_throttled_after_max_failed_attempts(client, regular_user, settings):
    settings.LOGIN_THROTTLE_MAX_ATTEMPTS = 3

    for _ in range(3):
        response = client.post(reverse('login'), {
            'username': 'alice', 'password': 'WrongPassword',
        })
        assert response.status_code == 200

    # 4th attempt (even with the CORRECT password) should now be blocked
    response = client.post(reverse('login'), {
        'username': 'alice', 'password': 'TestPass123!',
    })
    assert response.status_code == 200
    assert not response.wsgi_request.user.is_authenticated
    assert b'Too many failed login attempts' in response.content


@pytest.mark.django_db
def test_successful_login_resets_throttle_counter(client, regular_user, settings):
    settings.LOGIN_THROTTLE_MAX_ATTEMPTS = 3

    client.post(reverse('login'), {'username': 'alice', 'password': 'Wrong1'})
    client.post(reverse('login'), {'username': 'alice', 'password': 'Wrong2'})

    # Correct password on the 3rd attempt succeeds and clears the counter
    response = client.post(reverse('login'), {
        'username': 'alice', 'password': 'TestPass123!',
    })
    assert response.status_code == 302

    client.logout()

    # Should be able to fail twice more without being locked out,
    # since the earlier counter was reset by the successful login above.
    response = client.post(reverse('login'), {'username': 'alice', 'password': 'Wrong3'})
    assert b'Too many failed login attempts' not in response.content


# --- Dashboard access & task CRUD ---

@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse('dashboard'))
    assert response.status_code == 302
    assert reverse('login') in response.url


@pytest.mark.django_db
def test_dashboard_accessible_when_logged_in(logged_in_client):
    response = logged_in_client.get(reverse('dashboard'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_add_task(logged_in_client, regular_user):
    response = logged_in_client.post(reverse('task_create'), {
        'title': 'Finish assignment',
    })
    assert response.status_code == 302
    assert Task.objects.filter(user=regular_user, title='Finish assignment').exists()


@pytest.mark.django_db
def test_toggle_task_completion(logged_in_client, regular_user):
    task = Task.objects.create(user=regular_user, title='Test task')
    assert task.completed is False

    logged_in_client.post(reverse('task_toggle', args=[task.id]))
    task.refresh_from_db()
    assert task.completed is True


@pytest.mark.django_db
def test_delete_task(logged_in_client, regular_user):
    task = Task.objects.create(user=regular_user, title='Delete me')
    logged_in_client.post(reverse('task_delete', args=[task.id]))
    assert not Task.objects.filter(id=task.id).exists()


@pytest.mark.django_db
def test_user_cannot_modify_another_users_task(logged_in_client, regular_user, db):
    other_user = User.objects.create_user(username='mallory', password='x')
    other_task = Task.objects.create(user=other_user, title='Not yours')

    response = logged_in_client.post(reverse('task_delete', args=[other_task.id]))
    assert response.status_code == 404
    assert Task.objects.filter(id=other_task.id).exists()  # untouched


# --- Creating tasks ---

def _today():
    return timezone.localdate()


@pytest.mark.django_db
def test_create_task_with_all_fields(logged_in_client, regular_user):
    due = _today() + timedelta(days=3)
    response = logged_in_client.post(reverse('task_create'), {
        'title': 'Write report',
        'description': 'Quarterly numbers',
        'due_date': due.isoformat(),
        'priority': Task.Priority.HIGH,
    })
    assert response.status_code == 302
    task = Task.objects.get(user=regular_user, title='Write report')
    assert task.description == 'Quarterly numbers'
    assert task.due_date == due
    assert task.priority == Task.Priority.HIGH
    assert task.completed is False


@pytest.mark.django_db
def test_create_task_defaults_to_medium_priority(logged_in_client, regular_user):
    logged_in_client.post(reverse('task_create'), {'title': 'No priority given'})
    assert Task.objects.get(title='No priority given').priority == Task.Priority.MEDIUM


@pytest.mark.django_db
def test_create_task_rejects_blank_title(logged_in_client, regular_user):
    response = logged_in_client.post(reverse('task_create'), {'title': '   '}, follow=True)
    assert not Task.objects.exists()
    assert b'Task title cannot be empty.' in response.content


@pytest.mark.django_db
def test_create_task_rejects_past_due_date(logged_in_client, regular_user):
    yesterday = _today() - timedelta(days=1)
    response = logged_in_client.post(reverse('task_create'), {
        'title': 'Too late', 'due_date': yesterday.isoformat(),
    }, follow=True)
    assert not Task.objects.exists()
    assert b'Due date cannot be in the past.' in response.content


@pytest.mark.django_db
def test_create_task_allows_due_today(logged_in_client, regular_user):
    logged_in_client.post(reverse('task_create'), {
        'title': 'Due today', 'due_date': _today().isoformat(),
    })
    assert Task.objects.filter(title='Due today').exists()


@pytest.mark.django_db
def test_create_task_requires_login(client, regular_user):
    response = client.post(reverse('task_create'), {'title': 'Sneaky'})
    assert response.status_code == 302
    assert reverse('login') in response.url
    assert not Task.objects.exists()


# --- Editing tasks ---

@pytest.mark.django_db
def test_edit_page_shows_task(logged_in_client, regular_user):
    task = Task.objects.create(user=regular_user, title='Edit me')
    response = logged_in_client.get(reverse('task_update', args=[task.id]))
    assert response.status_code == 200
    assert b'Edit me' in response.content


@pytest.mark.django_db
def test_edit_task_saves_changes(logged_in_client, regular_user):
    task = Task.objects.create(user=regular_user, title='Old title')
    response = logged_in_client.post(reverse('task_update', args=[task.id]), {
        'title': 'New title',
        'description': 'Now with details',
        'priority': Task.Priority.LOW,
        'completed': 'on',
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.title == 'New title'
    assert task.description == 'Now with details'
    assert task.priority == Task.Priority.LOW
    assert task.completed is True


@pytest.mark.django_db
def test_edit_keeps_existing_past_due_date(logged_in_client, regular_user):
    last_week = _today() - timedelta(days=7)
    task = Task.objects.create(user=regular_user, title='Overdue', due_date=last_week)
    response = logged_in_client.post(reverse('task_update', args=[task.id]), {
        'title': 'Overdue, renamed', 'due_date': last_week.isoformat(),
        'priority': Task.Priority.MEDIUM,
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.title == 'Overdue, renamed'


@pytest.mark.django_db
def test_edit_task_with_blank_title_shows_error(logged_in_client, regular_user):
    task = Task.objects.create(user=regular_user, title='Keep me')
    response = logged_in_client.post(reverse('task_update', args=[task.id]), {'title': ''})
    assert response.status_code == 200
    assert b'Task title cannot be empty.' in response.content
    task.refresh_from_db()
    assert task.title == 'Keep me'


# --- POST-only views ---

@pytest.mark.django_db
@pytest.mark.parametrize('url_name', ['task_toggle', 'task_delete'])
def test_toggle_and_delete_reject_get(logged_in_client, regular_user, url_name):
    task = Task.objects.create(user=regular_user, title='Safe')
    response = logged_in_client.get(reverse(url_name, args=[task.id]))
    assert response.status_code == 405
    task.refresh_from_db()
    assert task.completed is False


@pytest.mark.django_db
def test_create_rejects_get(logged_in_client):
    assert logged_in_client.get(reverse('task_create')).status_code == 405


@pytest.mark.django_db
def test_dashboard_rejects_post(logged_in_client):
    response = logged_in_client.post(reverse('dashboard'), {'action': 'add', 'title': 'Old way'})
    assert response.status_code == 405
    assert not Task.objects.exists()


# --- Other users' tasks ---

@pytest.fixture
def other_users_task(db):
    other_user = User.objects.create_user(username='mallory', password='x')
    return Task.objects.create(user=other_user, title='Not yours')


@pytest.mark.django_db
def test_user_cannot_view_edit_page_for_another_users_task(logged_in_client, other_users_task):
    response = logged_in_client.get(reverse('task_update', args=[other_users_task.id]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_user_cannot_edit_another_users_task(logged_in_client, other_users_task):
    response = logged_in_client.post(reverse('task_update', args=[other_users_task.id]), {
        'title': 'Hijacked', 'priority': Task.Priority.HIGH, 'completed': 'on',
    })
    assert response.status_code == 404
    other_users_task.refresh_from_db()
    assert other_users_task.title == 'Not yours'
    assert other_users_task.completed is False


@pytest.mark.django_db
def test_user_cannot_toggle_another_users_task(logged_in_client, other_users_task):
    response = logged_in_client.post(reverse('task_toggle', args=[other_users_task.id]))
    assert response.status_code == 404
    other_users_task.refresh_from_db()
    assert other_users_task.completed is False


@pytest.mark.django_db
def test_dashboard_only_lists_own_tasks(logged_in_client, regular_user, other_users_task):
    Task.objects.create(user=regular_user, title='Mine')
    response = logged_in_client.get(reverse('dashboard'))
    titles = [t.title for t in response.context['tasks']]
    assert titles == ['Mine']


# --- Redirecting back with filters ---

@pytest.mark.django_db
def test_toggle_redirects_back_to_filtered_page(logged_in_client, regular_user):
    task = Task.objects.create(user=regular_user, title='Filtered')
    next_url = reverse('dashboard') + '?status=active&sort=due&page=2'
    response = logged_in_client.post(reverse('task_toggle', args=[task.id]), {'next': next_url})
    assert response.status_code == 302
    assert response.url == next_url


@pytest.mark.django_db
def test_delete_redirects_back_to_filtered_page(logged_in_client, regular_user):
    task = Task.objects.create(user=regular_user, title='Filtered')
    next_url = reverse('dashboard') + '?priority=3&q=report'
    response = logged_in_client.post(reverse('task_delete', args=[task.id]), {'next': next_url})
    assert response.url == next_url


@pytest.mark.django_db
@pytest.mark.parametrize('bad_next', ['https://evil.example.com/', '//evil.example.com/'])
def test_redirect_ignores_external_next(logged_in_client, regular_user, bad_next):
    task = Task.objects.create(user=regular_user, title='Safe')
    response = logged_in_client.post(reverse('task_toggle', args=[task.id]), {'next': bad_next})
    assert response.url == reverse('dashboard')


# --- Dashboard filtering, search, sorting and pagination ---

def _titles(response):
    return [t.title for t in response.context['tasks']]


@pytest.mark.django_db
def test_dashboard_filters_by_status(logged_in_client, regular_user):
    Task.objects.create(user=regular_user, title='Open')
    Task.objects.create(user=regular_user, title='Done', completed=True)

    url = reverse('dashboard')
    assert set(_titles(logged_in_client.get(url))) == {'Open', 'Done'}
    assert _titles(logged_in_client.get(url, {'status': 'active'})) == ['Open']
    assert _titles(logged_in_client.get(url, {'status': 'completed'})) == ['Done']


@pytest.mark.django_db
def test_dashboard_filters_by_priority(logged_in_client, regular_user):
    Task.objects.create(user=regular_user, title='Urgent', priority=Task.Priority.HIGH)
    Task.objects.create(user=regular_user, title='Someday', priority=Task.Priority.LOW)
    response = logged_in_client.get(reverse('dashboard'), {'priority': Task.Priority.HIGH})
    assert _titles(response) == ['Urgent']


@pytest.mark.django_db
def test_dashboard_ignores_invalid_filters(logged_in_client, regular_user):
    Task.objects.create(user=regular_user, title='Anything')
    response = logged_in_client.get(reverse('dashboard'), {
        'status': 'bogus', 'priority': 'urgent', 'sort': 'nope', 'page': 'abc',
    })
    assert response.status_code == 200
    assert _titles(response) == ['Anything']


@pytest.mark.django_db
def test_dashboard_search_by_title(logged_in_client, regular_user):
    Task.objects.create(user=regular_user, title='Buy milk')
    Task.objects.create(user=regular_user, title='Write REPORT')
    response = logged_in_client.get(reverse('dashboard'), {'q': 'report'})
    assert _titles(response) == ['Write REPORT']


@pytest.mark.django_db
def test_dashboard_sorts_by_priority_high_to_low(logged_in_client, regular_user):
    # Created in an order that alphabetical or newest-first sorting would get wrong.
    Task.objects.create(user=regular_user, title='Medium', priority=Task.Priority.MEDIUM)
    Task.objects.create(user=regular_user, title='High', priority=Task.Priority.HIGH)
    Task.objects.create(user=regular_user, title='Low', priority=Task.Priority.LOW)
    response = logged_in_client.get(reverse('dashboard'), {'sort': 'priority'})
    assert _titles(response) == ['High', 'Medium', 'Low']


@pytest.mark.django_db
def test_dashboard_sorts_by_due_date_with_undated_last(logged_in_client, regular_user):
    today = _today()
    Task.objects.create(user=regular_user, title='No date')
    Task.objects.create(user=regular_user, title='Next week', due_date=today + timedelta(days=7))
    Task.objects.create(user=regular_user, title='Tomorrow', due_date=today + timedelta(days=1))
    response = logged_in_client.get(reverse('dashboard'), {'sort': 'due'})
    assert _titles(response) == ['Tomorrow', 'Next week', 'No date']


@pytest.mark.django_db
def test_dashboard_paginates_ten_per_page(logged_in_client, regular_user):
    for i in range(12):
        Task.objects.create(user=regular_user, title=f'Task {i}')
    url = reverse('dashboard')

    page1 = logged_in_client.get(url)
    assert len(page1.context['tasks']) == 10
    assert page1.context['page_obj'].paginator.num_pages == 2

    page2 = logged_in_client.get(url, {'page': 2})
    assert len(page2.context['tasks']) == 2


@pytest.mark.django_db
def test_pagination_links_keep_filters(logged_in_client, regular_user):
    for i in range(11):
        Task.objects.create(user=regular_user, title=f'Task {i}')
    response = logged_in_client.get(reverse('dashboard'), {'status': 'active', 'sort': 'due'})
    assert b'status=active&amp;sort=due&amp;page=2' in response.content


@pytest.mark.django_db
def test_overdue_tasks_are_highlighted(logged_in_client, regular_user):
    yesterday = _today() - timedelta(days=1)
    overdue = Task.objects.create(user=regular_user, title='Late', due_date=yesterday)
    done = Task.objects.create(user=regular_user, title='Late but done', due_date=yesterday, completed=True)
    future = Task.objects.create(user=regular_user, title='Later', due_date=_today() + timedelta(days=1))

    assert overdue.is_overdue is True
    assert done.is_overdue is False
    assert future.is_overdue is False

    response = logged_in_client.get(reverse('dashboard'))
    assert response.content.count(b'overdue-badge">Overdue</span>') == 1


# --- Role-based permissions ---

@pytest.mark.django_db
def test_admin_dashboard_requires_login(client):
    response = client.get(reverse('admin_dashboard'))
    assert response.status_code == 302
    assert reverse('login') in response.url


@pytest.mark.django_db
def test_admin_dashboard_forbidden_for_regular_user(logged_in_client):
    response = logged_in_client.get(reverse('admin_dashboard'))
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_dashboard_allowed_for_staff_user(logged_in_staff_client):
    response = logged_in_staff_client.get(reverse('admin_dashboard'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_dashboard_shows_all_users_tasks(logged_in_staff_client, regular_user, staff_user):
    Task.objects.create(user=regular_user, title="Alice's task")
    response = logged_in_staff_client.get(reverse('admin_dashboard'))
    assert b"Alice&#x27;s task" in response.content or b"Alice's task" in response.content


# --- Password reset ---

@pytest.mark.django_db
def test_password_reset_sends_email(client, regular_user):
    response = client.post(reverse('password_reset'), {'email': 'alice@example.com'})
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    assert 'alice' in mail.outbox[0].body.lower() or 'reset' in mail.outbox[0].subject.lower()


@pytest.mark.django_db
def test_password_reset_unknown_email_does_not_error(client):
    # Django deliberately doesn't reveal whether an email is registered
    response = client.post(reverse('password_reset'), {'email': 'nobody@example.com'})
    assert response.status_code == 302
    assert len(mail.outbox) == 0
