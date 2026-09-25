import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Choice, Module, Participant, Question, QuizSession, User


def make_teacher():
    return User.objects.create_user(
        username="teacher1", password="pw12345", role="teacher"
    )


def make_module(teacher, n=2):
    m = Module.objects.create(title="Module X", teacher=teacher)
    for i in range(n):
        q = Question.objects.create(
            module=m, text=f"Question {i + 1}", time_limit=60
        )
        Choice.objects.create(question=q, text="Right", is_correct=True, order=1)
        Choice.objects.create(question=q, text="Wrong A", order=2)
        Choice.objects.create(question=q, text="Wrong B", order=3)
    return m


class AuthTests(TestCase):
    def test_signup_teacher(self):
        resp = self.client.post(
            reverse("signup"),
            {
                "username": "newteacher",
                "email": "t@example.com",
                "role": "teacher",
                "password1": "password123!",
                "password2": "password123!",
            },
        )
        self.assertEqual(resp.status_code, 302)
        u = User.objects.get(username="newteacher")
        self.assertTrue(u.is_teacher)


class ModuleTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.client.force_login(self.teacher)

    def test_create_module_and_questions(self):
        resp = self.client.post(
            reverse("module_create"), {"title": "CS 101", "description": "d"}
        )
        self.assertEqual(resp.status_code, 302)
        m = Module.objects.get(title="CS 101")
        self.assertEqual(m.teacher, self.teacher)

        resp = self.client.post(
            reverse("question_create", args=[m.id]),
            {
                "text": "What is 2+2?",
                "time_limit": 30,
                "choice_1": "4",
                "choice_2": "5",
                "choice_3": "",
                "choice_4": "",
                "correct_choice": "1",
            },
        )
        self.assertEqual(resp.status_code, 302)
        q = Question.objects.get(module=m)
        self.assertEqual(q.choices.filter(is_correct=True).count(), 1)

    def test_question_requires_two_choices(self):
        m = make_module(self.teacher)
        resp = self.client.post(
            reverse("question_create", args=[m.id]),
            {
                "text": "Only one choice",
                "time_limit": 30,
                "choice_1": "A",
                "choice_2": "",
                "choice_3": "",
                "choice_4": "",
                "correct_choice": "1",
            },
        )
        self.assertIn("at least 2 choices", resp.content.decode().lower())

    def test_question_minimum_time_enforced(self):
        m = make_module(self.teacher)
        resp = self.client.post(
            reverse("question_create", args=[m.id]),
            {
                "text": "Too fast",
                "time_limit": 5,
                "choice_1": "A",
                "choice_2": "B",
                "choice_3": "",
                "choice_4": "",
                "correct_choice": "1",
            },
        )
        self.assertIn("10 seconds", resp.content.decode().lower())
        self.assertFalse(Question.objects.filter(text="Too fast").exists())


class QuizFlowTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.module = make_module(self.teacher, n=3)
        self.client.force_login(self.teacher)

    def test_full_flow(self):
        # Host
        resp = self.client.post(reverse("start_quiz", args=[self.module.id]))
        self.assertEqual(resp.status_code, 302)
        session = QuizSession.objects.get(module=self.module)
        self.assertEqual(len(session.code), 6)
        self.assertEqual(session.status, QuizSession.Status.WAITING)

        # Host starts question 1
        self.client.post(reverse("host_start_question", args=[session.code]))
        session.refresh_from_db()
        self.assertEqual(session.status, QuizSession.Status.QUESTION)
        self.assertEqual(session.current_index, 0)

        # Student joins
        student = self.client.__class__()
        resp = student.post(reverse("join"), {"code": session.code}, follow=True)
        self.assertEqual(resp.status_code, 200)
        resp = student.post(
            reverse("join_name", args=[session.code]), {"name": "Amina"}, follow=True
        )
        self.assertContains(resp, "Amina")

        # Student answers correctly
        question = session.current_question
        correct = question.choices.get(is_correct=True)
        resp = student.post(
            reverse("submit_answer", args=[session.code]),
            {"choice_id": correct.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        data = json.loads(resp.content)
        self.assertTrue(data["ok"])
        self.assertTrue(data["correct"])

        # Fast answer should earn points, capped at 1000
        part = Participant.objects.get(session=session, name="Amina")
        self.assertGreater(part.score, 0)
        self.assertLessEqual(part.score, 1000)

        # Force time expiry -> reveal
        session.question_ends_at = timezone.now() - timedelta(seconds=1)
        session.save()
        resp = student.get(reverse("quiz_state", args=[session.code]))
        data = json.loads(resp.content)
        self.assertEqual(data["status"], QuizSession.Status.REVEAL)
        self.assertEqual(data["my_answer"]["correct"], True)

        # Host advances to end
        self.client.post(reverse("host_next_question", args=[session.code]))
        self.client.post(reverse("host_next_question", args=[session.code]))
        self.client.post(reverse("host_next_question", args=[session.code]))
        session.refresh_from_db()
        self.assertEqual(session.status, QuizSession.Status.ENDED)

        # Student state returns leaderboard
        resp = student.get(reverse("quiz_state", args=[session.code]))
        data = json.loads(resp.content)
        self.assertEqual(data["status"], QuizSession.Status.ENDED)
        self.assertEqual(len(data["leaderboard"]), 1)

    def test_duplicate_answer_rejected(self):
        session = QuizSession.objects.create(module=self.module, host=self.teacher)
        self.client.post(reverse("host_start_question", args=[session.code]))
        session.refresh_from_db()
        student = self.client.__class__()
        student.post(reverse("join"), {"code": session.code}, follow=True)
        student.post(
            reverse("join_name", args=[session.code]), {"name": "Bob"}, follow=True
        )
        q = session.current_question
        correct = q.choices.get(is_correct=True)

        student.post(
            reverse("submit_answer", args=[session.code]), {"choice_id": correct.id}
        )
        resp = student.post(
            reverse("submit_answer", args=[session.code]), {"choice_id": correct.id}
        )
        self.assertFalse(json.loads(resp.content)["ok"])

    def test_invalid_choice_id_returns_error_not_500(self):
        session = QuizSession.objects.create(module=self.module, host=self.teacher)
        self.client.post(reverse("host_start_question", args=[session.code]))
        session.refresh_from_db()
        student = self.client.__class__()
        student.post(reverse("join"), {"code": session.code}, follow=True)
        student.post(
            reverse("join_name", args=[session.code]), {"name": "Zoe"}, follow=True
        )
        resp = student.post(
            reverse("submit_answer", args=[session.code]), {"choice_id": 999999}
        )
        data = json.loads(resp.content)
        self.assertFalse(data["ok"])