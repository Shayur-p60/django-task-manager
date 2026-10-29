from django.contrib.auth import views as auth_views
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from ..forms import ThrottledAuthenticationForm
from .views import ObtainTokenView, TaskViewSet

router = DefaultRouter()
router.register('tasks', TaskViewSet, basename='task')

# Log in/out links for the browsable API. These replace DRF's own
# rest_framework.urls so the login there uses the same throttled form
# as the rest of the site.
browsable_api_auth = ([
    path('login/', auth_views.LoginView.as_view(
        template_name='rest_framework/login.html',
        authentication_form=ThrottledAuthenticationForm,
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
], 'rest_framework')

urlpatterns = [
    path('', include(router.urls)),
    path('token/', ObtainTokenView.as_view(), name='api_token'),
    path('auth/', include(browsable_api_auth)),
    path('schema/', SpectacularAPIView.as_view(), name='api_schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api_schema'), name='api_docs'),
]
