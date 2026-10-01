from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from quiz.models import (
    ActivityLog,
    Answer,
    Choice,
    Module,
    Participant,
    Question,
    QuizSession,
    TeacherUtil,
    log_activity,
)

User = get_user_model()

PROFILE_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "phone",
    "whatsapp",
    "telegram",
    "facebook",
    "instagram",
    "youtube",
    "tiktok",
    "website",
)


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "whatsapp",
            "telegram",
            "facebook",
            "instagram",
            "youtube",
            "tiktok",
            "website",
            "role",
            "display_name",
            "initials",
            "date_joined",
        )
        read_only_fields = ("id", "username", "role", "date_joined")

    def get_display_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_initials(self, obj):
        name = obj.get_full_name().strip() or obj.username
        parts = [p for p in name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def validate_email(self, value):
        value = (value or "").strip().lower()
        if not value:
            return value
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "That email is already used by another account."
            )
        return value


class StudentRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = (
            "username",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "email",
        )

    def validate_username(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Username is required.")
        if len(value) < 3:
            raise serializers.ValidationError(
                "Username must be at least 3 characters."
            )
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "The two passwords do not match."}
            )
        validate_password(attrs.get("password") or "")
        email = (attrs.get("email") or "").strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                {"email": "That email is already used by another account."}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm", None)
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.role = User.Role.STUDENT
        user.set_password(password)
        user.save()
        log_activity(user, ActivityLog.Action.SIGNUP, user.username)
        return user


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Your current password is wrong.")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        log_activity(user, ActivityLog.Action.PASSWORD_CHANGED, user.username)
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"})

    def validate(self, attrs):
        username = (attrs.get("username") or "").strip()
        password = attrs.get("password") or ""
        user = User.objects.filter(username__iexact=username).first()
        if user is None:
            user = User.objects.filter(email__iexact=username).first()
        if user is None or not user.check_password(password):
            raise serializers.ValidationError(
                {"detail": "Wrong username or password."}
            )
        if user.is_archived or not user.is_active:
            raise serializers.ValidationError(
                {"detail": "This account has been deactivated."}
            )
        attrs["user"] = user
        return attrs


class ChoiceSerializer(serializers.ModelSerializer):
    letter = serializers.SerializerMethodField()

    class Meta:
        model = Choice
        fields = ("id", "text", "letter")

    def get_letter(self, obj):
        choices = list(obj.question.choices.all())
        if obj in choices:
            return chr(65 + choices.index(obj))
        return "?"


class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ("id", "text", "time_limit", "order", "choices")


class AnswerResultSerializer(serializers.ModelSerializer):
    choice_text = serializers.CharField(source="choice.text", read_only=True)
    correct = serializers.BooleanField(source="choice.is_correct", read_only=True)

    class Meta:
        model = Answer
        fields = (
            "id",
            "question_id",
            "choice_id",
            "choice_text",
            "correct",
            "points_earned",
            "answered_at",
        )


class ParticipantSerializer(serializers.ModelSerializer):
    correct_count = serializers.SerializerMethodField()
    answered_count = serializers.SerializerMethodField()
    accuracy = serializers.SerializerMethodField()
    rank = serializers.SerializerMethodField()

    class Meta:
        model = Participant
        fields = (
            "id",
            "name",
            "team",
            "score",
            "rank",
            "correct_count",
            "answered_count",
            "accuracy",
            "joined_at",
        )

    def get_correct_count(self, obj):
        return obj.answers.filter(choice__is_correct=True).count()

    def get_answered_count(self, obj):
        return obj.answers.count()

    def get_accuracy(self, obj):
        answered = obj.answers.count()
        if not answered:
            return 0
        correct = obj.answers.filter(choice__is_correct=True).count()
        return round(correct / answered * 100)

    def get_rank(self, obj):
        cached = self.context.get("ranks")
        if cached is None:
            return None
        return cached.get(obj.id)


class JoinSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6)
    nickname = serializers.CharField(max_length=100)
    team = serializers.ChoiceField(
        choices=Participant.Team.choices, required=False, allow_blank=True
    )

    def validate_code(self, value):
        return (value or "").strip().upper()

    def validate_nickname(self, value):
        value = (value or "").strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                "Enter a name with at least 2 characters."
            )
        return value

    def validate(self, attrs):
        session = QuizSession.objects.filter(code=attrs["code"]).first()
        if session is None:
            raise serializers.ValidationError({"code": "No quiz found for that code."})
        if session.status == QuizSession.Status.ENDED:
            raise serializers.ValidationError(
                {"code": "This quiz has already ended."}
            )
        name = attrs["nickname"]
        if Participant.objects.filter(session=session, name=name).exists():
            raise serializers.ValidationError(
                {"nickname": "That name is taken here. Pick another."}
            )
        attrs["session"] = session
        if session.teams_enabled and not attrs.get("team"):
            raise serializers.ValidationError(
                {"team": "Choose your team before joining."}
            )
        if not session.teams_enabled:
            attrs["team"] = ""
        return attrs


class SubmitAnswerSerializer(serializers.Serializer):
    choice_id = serializers.IntegerField()

    def validate_choice_id(self, value):
        return value


class ModuleSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = (
            "id",
            "title",
            "description",
            "question_count",
            "teacher_name",
            "created_at",
        )

    def get_question_count(self, obj):
        return obj.questions.filter(is_active=True).count()

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.username


class TeacherUtilSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    category_label = serializers.CharField(
        source="get_category_display", read_only=True
    )
    filename = serializers.CharField(read_only=True)
    file_url = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()

    class Meta:
        model = TeacherUtil
        fields = (
            "id",
            "title",
            "description",
            "category",
            "category_label",
            "filename",
            "file_url",
            "file_size",
            "teacher_name",
            "created_at",
        )

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.username

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get("request")
        url = obj.file.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url

    def get_file_size(self, obj):
        try:
            return obj.file.size
        except (OSError, ValueError):
            return None


class UtilTeacherSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.SerializerMethodField()
    file_count = serializers.IntegerField()

    def get_name(self, obj):
        return obj.get_full_name() or obj.username
