import hashlib
import secrets

from django.conf import settings
from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS

from quiz.models import Participant, QuizSession, User

TICKET_HEADER = 'HTTP_X_QUIZ_TICKET'


def new_ticket():
    return secrets.token_urlsafe(32)


def hash_ticket(ticket):
    return hashlib.sha256(ticket.encode()).hexdigest()


def get_ticket_from_request(request):
    return request.META.get(TICKET_HEADER, '').strip()


def participant_for_ticket(session, ticket):
    if not ticket:
        return None
    return Participant.objects.filter(
        session=session, api_token=hash_ticket(ticket)
    ).first()


def participant_for_user(session, user):
    if not user or not user.is_authenticated:
        return None
    return (
        Participant.objects.filter(session=session, user=user)
        .order_by('-id')
        .first()
    )


class IsActiveNotArchived(permissions.BasePermission):
    message = 'This account has been deactivated.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and not user.is_archived
        )


class IsStudent(IsActiveNotArchived):
    message = 'This action is for student accounts only.'

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.role == getattr(
            settings, 'MOBILE_API', {}
        ).get('STUDENT_ROLE', User.Role.STUDENT)


def resolve_session(code):
    return QuizSession.objects.filter(code=code.strip().upper()).first()


def is_owner(user, obj):
    return bool(user and user.is_authenticated and obj == user)


READ_ONLY = SAFE_METHODS
