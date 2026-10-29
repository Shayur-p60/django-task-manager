from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from ..forms import ThrottledAuthenticationForm
from ..models import Task
from .filters import TaskFilter
from .serializers import TaskSerializer, TokenRequestSerializer, TokenResponseSerializer

TRUE_VALUES = {'1', 'true', 'yes'}


@extend_schema_view(
    list=extend_schema(parameters=[
        OpenApiParameter(
            'all', OpenApiTypes.BOOL,
            description='Staff only: list every user\'s tasks. Ignored for other users.',
        ),
    ]),
)
class TaskViewSet(viewsets.ModelViewSet):
    """
    CRUD for the signed-in user's tasks. Tasks belonging to other users
    return 404, including for staff; staff can only *list* everyone's
    tasks, with ?all=true.
    """
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TaskFilter
    search_fields = ['title']
    ordering_fields = ['due_date', 'priority', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        tasks = Task.objects.select_related('user')
        if getattr(self, 'swagger_fake_view', False):
            return tasks.none()  # schema generation, no real user
        if self.action == 'list' and self._wants_all_tasks():
            return tasks
        return tasks.filter(user=self.request.user)

    def _wants_all_tasks(self):
        requested = self.request.query_params.get('all', '').strip().lower() in TRUE_VALUES
        return requested and self.request.user.is_staff

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ObtainTokenView(APIView):
    """
    Exchange a username and password for an API token.

    Two limits apply:
    - the same per-username lockout as the web login form
      (ThrottledAuthenticationForm), so the API can't be used to get
      around it;
    - a per-IP rate limit (DEFAULT_THROTTLE_RATES['api_token']).
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'api_token'

    @extend_schema(
        request=TokenRequestSerializer,
        responses={200: TokenResponseSerializer, 400: OpenApiTypes.OBJECT, 429: OpenApiTypes.OBJECT},
        auth=[],
    )
    def post(self, request):
        form = ThrottledAuthenticationForm(request._request, data=request.data)
        if form.is_valid():
            token, _ = Token.objects.get_or_create(user=form.get_user())
            return Response({'token': token.key})

        errors = form.errors.get_json_data()
        codes = {error['code'] for field_errors in errors.values() for error in field_errors}
        body = {
            ('non_field_errors' if field == '__all__' else field): [e['message'] for e in field_errors]
            for field, field_errors in errors.items()
        }
        if 'too_many_attempts' in codes:
            return Response(body, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response(body, status=status.HTTP_400_BAD_REQUEST)
