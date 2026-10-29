"""
Tests for the REST API under /api/: authentication, token endpoint,
user isolation, CRUD, filtering/search/ordering/pagination, and docs.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from .models import Task

PASSWORD = 'TestPass123!'
LIST_URL = '/api/tasks/'


def detail_url(task):
    return f'/api/tasks/{task.pk}/'


def today():
    return timezone.localdate()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def alice(db):
    return User.objects.create_user(username='alice', password=PASSWORD)


@pytest.fixture
def bob(db):
    return User.objects.create_user(username='bob', password=PASSWORD)


@pytest.fixture
def staff(db):
    return User.objects.create_user(username='staffer', password=PASSWORD, is_staff=True)


@pytest.fixture
def alice_client(alice):
    client = APIClient()
    token = Token.objects.create(user=alice)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


@pytest.fixture
def staff_client(staff):
    client = APIClient()
    client.force_authenticate(staff)
    return client


def titles(response):
    return [task['title'] for task in response.json()['results']]


# --- Authentication ---

@pytest.mark.django_db
@pytest.mark.parametrize('method', ['get', 'post'])
def test_list_requires_authentication(api_client, method):
    response = getattr(api_client, method)(LIST_URL, {'title': 'x'})
    assert response.status_code == 401
    assert response['WWW-Authenticate'] == 'Token'


@pytest.mark.django_db
@pytest.mark.parametrize('method', ['get', 'put', 'patch', 'delete'])
def test_detail_requires_authentication(api_client, alice, method):
    task = Task.objects.create(user=alice, title='Private')
    response = getattr(api_client, method)(detail_url(task), {'title': 'x'})
    assert response.status_code == 401
    assert Task.objects.get(pk=task.pk).title == 'Private'


@pytest.mark.django_db
def test_invalid_token_is_rejected(api_client):
    api_client.credentials(HTTP_AUTHORIZATION='Token not-a-real-token')
    assert api_client.get(LIST_URL).status_code == 401


@pytest.mark.django_db
def test_session_auth_works_for_browsable_api(client, alice):
    client.login(username='alice', password=PASSWORD)
    response = client.get(LIST_URL, HTTP_ACCEPT='text/html')
    assert response.status_code == 200
    assert b'Task List' in response.content


@pytest.mark.django_db
def test_browsable_api_login_page_renders(client):
    assert client.get(reverse('rest_framework:login')).status_code == 200


# --- Token endpoint ---

@pytest.mark.django_db
def test_obtain_token_with_valid_credentials(api_client, alice):
    response = api_client.post('/api/token/', {'username': 'alice', 'password': PASSWORD}, format='json')
    assert response.status_code == 200
    token = response.json()['token']
    assert token == Token.objects.get(user=alice).key

    # The token then works for API calls.
    api_client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
    assert api_client.get(LIST_URL).status_code == 200


@pytest.mark.django_db
def test_obtain_token_returns_same_token_each_time(api_client, alice):
    first = api_client.post('/api/token/', {'username': 'alice', 'password': PASSWORD}).json()['token']
    second = api_client.post('/api/token/', {'username': 'alice', 'password': PASSWORD}).json()['token']
    assert first == second


@pytest.mark.django_db
def test_obtain_token_with_wrong_password(api_client, alice):
    response = api_client.post('/api/token/', {'username': 'alice', 'password': 'wrong'})
    assert response.status_code == 400
    assert 'non_field_errors' in response.json()
    assert not Token.objects.exists()


@pytest.mark.django_db
def test_obtain_token_with_missing_fields(api_client):
    response = api_client.post('/api/token/', {})
    assert response.status_code == 400
    assert set(response.json()) == {'username', 'password'}


@pytest.mark.django_db
def test_token_endpoint_locks_out_username_after_failed_attempts(api_client, alice, settings):
    settings.LOGIN_THROTTLE_MAX_ATTEMPTS = 3
    for _ in range(3):
        assert api_client.post('/api/token/', {'username': 'alice', 'password': 'wrong'}).status_code == 400

    # Even the correct password is now refused.
    response = api_client.post('/api/token/', {'username': 'alice', 'password': PASSWORD})
    assert response.status_code == 429
    assert 'Too many failed login attempts' in response.json()['non_field_errors'][0]
    assert not Token.objects.exists()


@pytest.mark.django_db
def test_token_lockout_is_shared_with_web_login(client, api_client, alice, settings):
    settings.LOGIN_THROTTLE_MAX_ATTEMPTS = 2
    for _ in range(2):
        client.post(reverse('login'), {'username': 'alice', 'password': 'wrong'})

    response = api_client.post('/api/token/', {'username': 'alice', 'password': PASSWORD})
    assert response.status_code == 429


@pytest.mark.django_db
def test_token_endpoint_rate_limited_per_ip(api_client, alice, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, 'THROTTLE_RATES', {'api_token': '2/minute'})
    for _ in range(2):
        assert api_client.post('/api/token/', {'username': 'alice', 'password': PASSWORD}).status_code == 200
    assert api_client.post('/api/token/', {'username': 'alice', 'password': PASSWORD}).status_code == 429


# --- User isolation ---

@pytest.fixture
def bobs_task(bob):
    return Task.objects.create(user=bob, title="Bob's task", priority=Task.Priority.LOW)


@pytest.mark.django_db
def test_list_only_shows_own_tasks(alice_client, alice, bobs_task):
    Task.objects.create(user=alice, title="Alice's task")
    response = alice_client.get(LIST_URL)
    assert titles(response) == ["Alice's task"]
    assert response.json()['count'] == 1


@pytest.mark.django_db
def test_cannot_read_another_users_task(alice_client, bobs_task):
    assert alice_client.get(detail_url(bobs_task)).status_code == 404


@pytest.mark.django_db
def test_cannot_update_another_users_task(alice_client, bobs_task):
    put = alice_client.put(detail_url(bobs_task), {'title': 'Hijacked', 'completed': True}, format='json')
    patch = alice_client.patch(detail_url(bobs_task), {'completed': True}, format='json')
    assert put.status_code == 404
    assert patch.status_code == 404
    bobs_task.refresh_from_db()
    assert bobs_task.title == "Bob's task"
    assert bobs_task.completed is False


@pytest.mark.django_db
def test_cannot_delete_another_users_task(alice_client, bobs_task):
    assert alice_client.delete(detail_url(bobs_task)).status_code == 404
    assert Task.objects.filter(pk=bobs_task.pk).exists()


@pytest.mark.django_db
def test_cannot_create_task_for_another_user(alice_client, alice, bob):
    response = alice_client.post(LIST_URL, {'title': 'Sneaky', 'user': bob.pk, 'owner': 'bob'}, format='json')
    assert response.status_code == 201
    assert Task.objects.get(title='Sneaky').user == alice
    assert response.json()['owner'] == 'alice'


@pytest.mark.django_db
@pytest.mark.parametrize('value', ['true', '1', 'yes'])
def test_staff_can_list_all_tasks_with_all_param(staff_client, staff, bobs_task, value):
    Task.objects.create(user=staff, title='Staff task')
    response = staff_client.get(LIST_URL, {'all': value})
    assert sorted(titles(response)) == ["Bob's task", 'Staff task']


@pytest.mark.django_db
def test_staff_without_all_param_sees_only_own_tasks(staff_client, staff, bobs_task):
    Task.objects.create(user=staff, title='Staff task')
    assert titles(staff_client.get(LIST_URL)) == ['Staff task']


@pytest.mark.django_db
def test_all_param_is_ignored_for_regular_users(alice_client, alice, bobs_task):
    Task.objects.create(user=alice, title="Alice's task")
    assert titles(alice_client.get(LIST_URL, {'all': 'true'})) == ["Alice's task"]


@pytest.mark.django_db
def test_staff_cannot_modify_other_users_tasks_through_api(staff_client, bobs_task):
    url = detail_url(bobs_task) + '?all=true'
    assert staff_client.get(url).status_code == 404
    assert staff_client.delete(url).status_code == 404
    assert Task.objects.filter(pk=bobs_task.pk).exists()


# --- CRUD happy paths ---

@pytest.mark.django_db
def test_create_task(alice_client, alice):
    due = today() + timedelta(days=2)
    response = alice_client.post(LIST_URL, {
        'title': 'Write report',
        'description': 'Quarterly numbers',
        'due_date': due.isoformat(),
        'priority': 'high',
    }, format='json')
    assert response.status_code == 201
    body = response.json()
    assert body['title'] == 'Write report'
    assert body['priority'] == 'high'
    assert body['due_date'] == due.isoformat()
    assert body['completed'] is False
    assert body['is_overdue'] is False

    task = Task.objects.get(pk=body['id'])
    assert task.user == alice
    assert task.priority == Task.Priority.HIGH


@pytest.mark.django_db
def test_create_task_defaults(alice_client):
    body = alice_client.post(LIST_URL, {'title': 'Minimal'}, format='json').json()
    assert body['priority'] == 'medium'
    assert body['description'] == ''
    assert body['due_date'] is None


@pytest.mark.django_db
def test_retrieve_task(alice_client, alice):
    task = Task.objects.create(user=alice, title='Read me', priority=Task.Priority.LOW)
    response = alice_client.get(detail_url(task))
    assert response.status_code == 200
    assert response.json()['title'] == 'Read me'
    assert response.json()['priority'] == 'low'


@pytest.mark.django_db
def test_full_update_task(alice_client, alice):
    task = Task.objects.create(user=alice, title='Old')
    response = alice_client.put(detail_url(task), {
        'title': 'New', 'description': 'Changed', 'priority': 'low', 'completed': True,
    }, format='json')
    assert response.status_code == 200
    task.refresh_from_db()
    assert (task.title, task.description, task.priority, task.completed) == (
        'New', 'Changed', Task.Priority.LOW, True,
    )


@pytest.mark.django_db
def test_partial_update_task(alice_client, alice):
    task = Task.objects.create(user=alice, title='Keep title')
    response = alice_client.patch(detail_url(task), {'completed': True}, format='json')
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.completed is True
    assert task.title == 'Keep title'


@pytest.mark.django_db
def test_delete_task(alice_client, alice):
    task = Task.objects.create(user=alice, title='Bye')
    assert alice_client.delete(detail_url(task)).status_code == 204
    assert not Task.objects.filter(pk=task.pk).exists()


@pytest.mark.django_db
def test_create_rejects_blank_title(alice_client):
    response = alice_client.post(LIST_URL, {'title': '   '}, format='json')
    assert response.status_code == 400
    assert 'title' in response.json()


@pytest.mark.django_db
def test_create_rejects_past_due_date(alice_client):
    yesterday = today() - timedelta(days=1)
    response = alice_client.post(LIST_URL, {'title': 'Late', 'due_date': yesterday.isoformat()}, format='json')
    assert response.status_code == 400
    assert response.json()['due_date'] == ['Due date cannot be in the past.']


@pytest.mark.django_db
def test_update_allows_existing_past_due_date(alice_client, alice):
    last_week = today() - timedelta(days=7)
    task = Task.objects.create(user=alice, title='Overdue', due_date=last_week)
    response = alice_client.patch(detail_url(task), {'title': 'Still overdue'}, format='json')
    assert response.status_code == 200
    assert response.json()['is_overdue'] is True


@pytest.mark.django_db
def test_create_rejects_unknown_priority(alice_client):
    response = alice_client.post(LIST_URL, {'title': 'x', 'priority': 'urgent'}, format='json')
    assert response.status_code == 400
    assert 'priority' in response.json()


@pytest.mark.django_db
def test_read_only_fields_are_ignored(alice_client, alice):
    task = Task.objects.create(user=alice, title='Fixed id')
    response = alice_client.patch(detail_url(task), {'id': 999, 'is_overdue': True}, format='json')
    assert response.status_code == 200
    assert response.json()['id'] == task.pk
    assert response.json()['is_overdue'] is False


# --- Filtering, search, ordering, pagination ---

@pytest.fixture
def mixed_tasks(alice):
    d = today()
    return [
        Task.objects.create(user=alice, title='Buy milk', priority=Task.Priority.LOW,
                            due_date=d + timedelta(days=5)),
        Task.objects.create(user=alice, title='Write report', priority=Task.Priority.HIGH,
                            due_date=d + timedelta(days=1), completed=True),
        Task.objects.create(user=alice, title='Report bug', priority=Task.Priority.MEDIUM,
                            due_date=d + timedelta(days=3)),
    ]


@pytest.mark.django_db
def test_filter_by_completed(alice_client, mixed_tasks):
    assert titles(alice_client.get(LIST_URL, {'completed': 'true'})) == ['Write report']
    assert sorted(titles(alice_client.get(LIST_URL, {'completed': 'false'}))) == ['Buy milk', 'Report bug']


@pytest.mark.django_db
def test_filter_by_priority(alice_client, mixed_tasks):
    assert titles(alice_client.get(LIST_URL, {'priority': 'high'})) == ['Write report']
    assert titles(alice_client.get(LIST_URL, {'priority': 'low'})) == ['Buy milk']


@pytest.mark.django_db
def test_filter_by_invalid_priority_returns_400(alice_client, mixed_tasks):
    assert alice_client.get(LIST_URL, {'priority': 'urgent'}).status_code == 400


@pytest.mark.django_db
def test_combined_filters(alice_client, mixed_tasks):
    response = alice_client.get(LIST_URL, {'completed': 'false', 'priority': 'medium'})
    assert titles(response) == ['Report bug']


@pytest.mark.django_db
def test_search_by_title(alice_client, mixed_tasks):
    assert sorted(titles(alice_client.get(LIST_URL, {'search': 'report'}))) == ['Report bug', 'Write report']


@pytest.mark.django_db
def test_ordering_by_priority(alice_client, mixed_tasks):
    assert titles(alice_client.get(LIST_URL, {'ordering': 'priority'})) == ['Buy milk', 'Report bug', 'Write report']
    assert titles(alice_client.get(LIST_URL, {'ordering': '-priority'})) == ['Write report', 'Report bug', 'Buy milk']


@pytest.mark.django_db
def test_ordering_by_due_date(alice_client, mixed_tasks):
    assert titles(alice_client.get(LIST_URL, {'ordering': 'due_date'})) == ['Write report', 'Report bug', 'Buy milk']


@pytest.mark.django_db
def test_ordering_by_created_at(alice_client, mixed_tasks):
    assert titles(alice_client.get(LIST_URL, {'ordering': 'created_at'})) == ['Buy milk', 'Write report', 'Report bug']
    # Default is newest first.
    assert titles(alice_client.get(LIST_URL)) == ['Report bug', 'Write report', 'Buy milk']


@pytest.mark.django_db
def test_ordering_by_unknown_field_is_ignored(alice_client, mixed_tasks):
    response = alice_client.get(LIST_URL, {'ordering': 'user__password'})
    assert response.status_code == 200
    assert titles(response) == ['Report bug', 'Write report', 'Buy milk']


@pytest.mark.django_db
def test_pagination(alice_client, alice):
    for i in range(12):
        Task.objects.create(user=alice, title=f'Task {i}')

    page1 = alice_client.get(LIST_URL).json()
    assert page1['count'] == 12
    assert len(page1['results']) == 10
    assert page1['next'] is not None
    assert page1['previous'] is None

    page2 = alice_client.get(LIST_URL, {'page': 2}).json()
    assert len(page2['results']) == 2
    assert page2['next'] is None


@pytest.mark.django_db
def test_pagination_keeps_filters_in_next_link(alice_client, alice):
    for i in range(11):
        Task.objects.create(user=alice, title=f'Task {i}', priority=Task.Priority.HIGH)
    next_link = alice_client.get(LIST_URL, {'priority': 'high'}).json()['next']
    assert 'priority=high' in next_link
    assert 'page=2' in next_link


# --- Docs ---

@pytest.mark.django_db
def test_openapi_schema_lists_task_endpoints(api_client):
    response = api_client.get('/api/schema/', {'format': 'json'})
    assert response.status_code == 200
    paths = response.json()['paths']
    assert '/api/tasks/' in paths
    assert '/api/tasks/{id}/' in paths
    assert '/api/token/' in paths


@pytest.mark.django_db
def test_swagger_docs_page(api_client):
    response = api_client.get('/api/docs/')
    assert response.status_code == 200
    assert b'swagger' in response.content.lower()
