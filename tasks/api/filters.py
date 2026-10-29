import django_filters

from ..models import Task
from .serializers import PRIORITY_NAMES


class TaskFilter(django_filters.FilterSet):
    completed = django_filters.BooleanFilter()
    priority = django_filters.ChoiceFilter(choices=PRIORITY_NAMES, method='filter_priority')

    class Meta:
        model = Task
        fields = ['completed', 'priority']

    def filter_priority(self, queryset, name, value):
        return queryset.filter(priority=Task.Priority[value.upper()])
