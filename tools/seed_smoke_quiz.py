"""Create a live quiz fixture for the Flutter app smoke test.

Run with:  python manage.py shell < tools/seed_smoke_quiz.py
Prints the quiz code and choice ids the Dart smoke test needs.
"""

from quiz.models import (
    Answer,
    Choice,
    Module,
    Participant,
    Question,
    QuizSession,
    User,
)

USERNAME = "smoketeacher"

teacher, _ = User.objects.get_or_create(
    username=USERNAME,
    defaults={
        "role": User.Role.TEACHER,
        "first_name": "Smoke",
        "last_name": "Teacher",
    },
)
teacher.role = User.Role.TEACHER
teacher.set_password("smoke-pass-123")
teacher.save()

module, _ = Module.objects.get_or_create(
    title="Smoke Module",
    teacher=teacher,
    defaults={"description": "Fixture for Flutter app smoke tests"},
)

module.questions.update(is_active=False)

# Start from a clean slate so repeated smoke runs are deterministic.
for old in QuizSession.objects.filter(module=module):
    Answer.objects.filter(participant__session=old).delete()
    Participant.objects.filter(session=old).delete()
    old.delete()

question = Question.objects.create(
    module=module,
    text="What is 2 + 2?",
    time_limit=30,
    order=1,
    is_active=True,
)
question.choices.all().delete()
correct = Choice.objects.create(question=question, text="4", is_correct=True, order=1)
Choice.objects.create(question=question, text="3", is_correct=False, order=2)
Choice.objects.create(question=question, text="5", is_correct=False, order=3)
Choice.objects.create(question=question, text="6", is_correct=False, order=4)

quiz = QuizSession.objects.create(module=module, host=teacher, teams_enabled=False)

print(f"CODE={quiz.code}")
print(f"QUESTION_ID={question.id}")
print(f"CORRECT_CHOICE_ID={correct.id}")
print(f"WRONG_CHOICE_ID={Choice.objects.filter(question=question, is_correct=False).order_by('order').first().id}")
print("SEEDED=1")
