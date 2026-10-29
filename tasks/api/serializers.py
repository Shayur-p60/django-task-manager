from django.utils import timezone
from rest_framework import serializers

from ..models import Task

# The API uses readable names ("low", "medium", "high") for priority,
# while the database stores 1/2/3 so it sorts correctly.
PRIORITY_NAMES = [(p.name.lower(), p.label) for p in Task.Priority]


class PriorityField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        super().__init__(choices=PRIORITY_NAMES, **kwargs)

    def to_representation(self, value):
        return Task.Priority(value).name.lower()

    def to_internal_value(self, data):
        name = super().to_internal_value(data)
        return Task.Priority[name.upper()]


class TaskSerializer(serializers.ModelSerializer):
    priority = PriorityField(required=False)
    owner = serializers.CharField(source='user.username', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'due_date', 'priority', 'completed',
            'is_overdue', 'owner', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_due_date(self, value):
        # Same rule as the web form: no past dates on create, but an
        # existing overdue task can still be updated.
        if self.instance is None and value and value < timezone.localdate():
            raise serializers.ValidationError('Due date cannot be in the past.')
        return value


class TokenRequestSerializer(serializers.Serializer):
    """Used only to describe the token endpoint in the OpenAPI docs."""
    username = serializers.CharField()
    password = serializers.CharField(style={'input_type': 'password'})


class TokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
