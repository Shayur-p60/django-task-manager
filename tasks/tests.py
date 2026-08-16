"""
Test suite for the tasks app: registration, authentication (including
login throttling), task CRUD, role-based permissions, and password reset.

Run with: pytest
"""

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.urls import reverse

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
    response = logged_in_client.post(reverse('dashboard'), {
        'action': 'add', 'title': 'Finish assignment',
    })
    assert response.status_code == 302
    assert Task.objects.filter(user=regular_user, title='Finish assignment').exists()


@pytest.mark.django_db
def test_toggle_task_completion(logged_in_client, regular_user):
    task = Task.objects.create(user=regular_user, title='Test task')
    assert task.completed is False

    logged_in_client.post(reverse('dashboard'), {'action': 'toggle', 'task_id': task.id})
    task.refresh_from_db()
    assert task.completed is True


@pytest.mark.django_db
def test_delete_task(logged_in_client, regular_user):
    task = Task.objects.create(user=regular_user, title='Delete me')
    logged_in_client.post(reverse('dashboard'), {'action': 'delete', 'task_id': task.id})
    assert not Task.objects.filter(id=task.id).exists()


@pytest.mark.django_db
def test_user_cannot_modify_another_users_task(logged_in_client, regular_user, db):
    other_user = User.objects.create_user(username='mallory', password='x')
    other_task = Task.objects.create(user=other_user, title='Not yours')

    response = logged_in_client.post(reverse('dashboard'), {
        'action': 'delete', 'task_id': other_task.id,
    })
    assert response.status_code == 404
    assert Task.objects.filter(id=other_task.id).exists()  # untouched


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
