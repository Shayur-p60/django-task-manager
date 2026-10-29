from django.contrib import admin
from django.urls import include, path
from tasks import views
from tasks.forms import ThrottledAuthenticationForm
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Health check for Docker / Render / Railway (exempt from the HTTPS redirect)
    path('healthz/', views.healthz, name='healthz'),

    # Custom views
    path('', views.dashboard, name='home'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('tasks/new/', views.task_create, name='task_create'),
    path('tasks/<int:pk>/edit/', views.task_update, name='task_update'),
    path('tasks/<int:pk>/toggle/', views.task_toggle, name='task_toggle'),
    path('tasks/<int:pk>/delete/', views.task_delete, name='task_delete'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # REST API (see tasks/api/) and its OpenAPI docs at /api/docs/
    path('api/', include('tasks.api.urls')),

    # Built-in auth views (login / logout). Login uses a throttled form —
    # see tasks/forms.py — to slow down brute-force credential attempts.
    path('login/',
         auth_views.LoginView.as_view(
             template_name='registration/login.html',
             authentication_form=ThrottledAuthenticationForm,
         ),
         name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Built-in password reset views
    path('password-reset/',
         auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'),
         name='password_reset'),
    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'),
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('reset/done/',
         auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'),
         name='password_reset_complete'),
]
