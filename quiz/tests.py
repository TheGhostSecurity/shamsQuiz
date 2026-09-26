import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Choice,
    Module,
    Participant,
    Question,
    QuizSession,
    RegistrationCode,
    User,
)


def make_student(username="student1"):
    return User.objects.create_user(
        username=username, password="pw12345", role="student"
    )


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


class RegistrationTests(TestCase):
    def test_student_registers_with_generated_code(self):
        code = RegistrationCode.objects.create(
            code=RegistrationCode.generate(),
            assigned_to="Ali",
            created_by=make_teacher(),
        )
        resp = self.client.post(
            reverse("register"), {"code": code.code}
        )
        self.assertEqual(resp.status_code, 302)

        resp = self.client.post(
            reverse("register_account"),
            {
                "username": "ali",
                "first_name": "Ali Hassan",
                "password1": "password123!",
                "password2": "password123!",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        u = User.objects.get(username="ali")
        self.assertEqual(u.role, User.Role.STUDENT)
        self.assertFalse(u.is_teacher)
        code.refresh_from_db()
        self.assertTrue(code.is_used)
        self.assertEqual(code.used_by, u)

    def test_code_cannot_be_used_twice(self):
        admin = make_teacher()
        code = RegistrationCode.objects.create(
            code=RegistrationCode.generate(), created_by=admin
        )
        s1 = make_student("first")
        code.used_by = s1
        code.used_at = timezone.now()
        code.save()
        # second attempt at same code fails loudly
        resp = self.client.post(reverse("register"), {"code": code.code})
        self.assertContains(
            resp, "already been used", status_code=200
        )

    def test_register_account_requires_code_first(self):
        resp = self.client.post(
            reverse("register_account"),
            {
                "username": "nopass",
                "password1": "password123!",
                "password2": "password123!",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse("register"))
        self.assertFalse(User.objects.filter(username="nopass").exists())

    def test_student_cannot_register_as_teacher(self):
        code = RegistrationCode.objects.create(
            code=RegistrationCode.generate(), created_by=make_teacher()
        )
        self.client.post(reverse("register"), {"code": code.code})
        resp = self.client.post(
            reverse("register_account"),
            {
                "username": "person",
                "password1": "password123!",
                "password2": "password123!",
            },
            follow=True,
        )
        u = User.objects.get(username="person")
        self.assertEqual(u.role, User.Role.STUDENT)  # role forced, never selectable
        self.assertFalse(u.is_teacher)


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

    def test_pause_resume_locks_answers(self):
        session = QuizSession.objects.create(module=self.module, host=self.teacher)
        self.client.post(reverse("host_start_question", args=[session.code]))
        session.refresh_from_db()
        student = self.client.__class__()
        student.post(reverse("join"), {"code": session.code}, follow=True)
        student.post(
            reverse("join_name", args=[session.code]), {"name": "Pia"}, follow=True
        )
        q = session.current_question
        correct = q.choices.get(is_correct=True)

        # pause -> answers locked for student
        self.client.post(reverse("host_pause", args=[session.code]))
        session.refresh_from_db()
        self.assertTrue(session.is_paused)
        resp = student.get(reverse("quiz_state", args=[session.code]))
        self.assertTrue(json.loads(resp.content)["paused"])
        resp = student.post(
            reverse("submit_answer", args=[session.code]), {"choice_id": correct.id}
        )
        self.assertFalse(json.loads(resp.content)["ok"])

        # resume -> answer accepted again
        self.client.post(reverse("host_resume", args=[session.code]))
        session.refresh_from_db()
        self.assertFalse(session.is_paused)
        part = Participant.objects.get(session=session, name="Pia")
        from django.core.cache import cache

        cache.delete(f"answer_rate_{part.id}")
        resp = student.post(
            reverse("submit_answer", args=[session.code]), {"choice_id": correct.id}
        )
        self.assertTrue(json.loads(resp.content)["ok"])

        # +15s extends the window
        before = session.question_ends_at
        self.client.post(reverse("host_add_time", args=[session.code]))
        session.refresh_from_db()
        self.assertGreater(session.question_ends_at, before)

    def test_teams_join_and_shuffle_deterministic(self):
        session = QuizSession.objects.create(
            module=self.module,
            host=self.teacher,
            teams_enabled=True,
        )
        self.client.post(reverse("host_start_question", args=[session.code]))
        session.refresh_from_db()
        student = self.client.__class__()
        student.post(reverse("join"), {"code": session.code}, follow=True)
        resp = student.post(
            reverse("join_name", args=[session.code]),
            {"name": "TeamRed", "team": "red"},
            follow=True,
        )
        part = Participant.objects.get(session=session, name="TeamRed")
        self.assertEqual(part.team, "red")
        resp = student.get(reverse("quiz_state", args=[session.code]))
        data = json.loads(resp.content)
        self.assertTrue(data["teams_enabled"])
        self.assertEqual(data["team"], "red")

        # same participant always sees the same (seeded) order
        order1 = [c["id"] for c in data["question"]["choices"]]
        data2 = json.loads(
            student.get(reverse("quiz_state", args=[session.code])).content
        )
        order2 = [c["id"] for c in data2["question"]["choices"]]
        self.assertEqual(order1, order2)
        self.assertEqual(sorted(order1), sorted(c.id for c in session.current_question.choices.all()))

    def test_answer_rate_limited(self):
        session = QuizSession.objects.create(module=self.module, host=self.teacher)
        self.client.post(reverse("host_start_question", args=[session.code]))
        session.refresh_from_db()
        student = self.client.__class__()
        student.post(reverse("join"), {"code": session.code}, follow=True)
        student.post(
            reverse("join_name", args=[session.code]), {"name": "Rush"}, follow=True
        )
        session.question_ends_at = timezone.now() + timedelta(seconds=30)
        session.save()
        # first (invalid) request warms the rate-limit key
        student.post(
            reverse("submit_answer", args=[session.code]), {"choice_id": 999999}
        )
        part = Participant.objects.get(session=session, name="Rush")
        from django.core.cache import cache

        cache.set(f"answer_rate_{part.id}", timezone.now().timestamp(), timeout=5)
        resp = student.post(
            reverse("submit_answer", args=[session.code]),
            {"choice_id": 999999},
        )
        self.assertEqual(resp.status_code, 429)
        self.assertFalse(json.loads(resp.content)["ok"])

    def test_module_duplicate_and_export_import(self):
        m = self.module
        q = m.questions.first()
        q.time_limit = 10
        q.save()
        resp = self.client.post(reverse("module_duplicate", args=[m.id]))
        copy = Module.objects.filter(title=f"{m.title} (copy)").first()
        self.assertIsNotNone(copy)
        self.assertEqual(copy.questions.count(), m.questions.count())

        resp = self.client.get(reverse("module_export_csv", args=[m.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(m.questions.first().text.encode(), resp.content)

        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_text = (
            "text,time_limit,choice_a,choice_b,choice_c,choice_d,correct\n"
            "Import q?,25,Option A,Option B,Option C,Option D,C\n"
        )
        resp = self.client.post(
            reverse("module_import_csv", args=[m.id]),
            {"csv_file": SimpleUploadedFile("q.csv", csv_text.encode(), content_type="text/csv")},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        m.refresh_from_db()
        new_q = m.questions.get(text="Import q?")
        self.assertEqual(new_q.time_limit, 25)
        self.assertEqual(new_q.choices.filter(is_correct=True).count(), 1)

    def test_teams_scoreboard_totals(self):
        session = QuizSession.objects.create(
            module=self.module,
            host=self.teacher,
            teams_enabled=True,
        )
        p_red = Participant.objects.create(
            session=session, name="Red One", team="red", score=500
        )
        Participant.objects.create(
            session=session, name="Blue One", team="blue", score=700
        )
        session.status = QuizSession.Status.ENDED
        session.ended_at = timezone.now()
        session.save()
        resp = self.client.get(reverse("scoreboard", args=[session.code]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Red", html)
        self.assertIn("Blue", html)


class StudentProgressTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student("progresskid")
        self.module = make_module(self.teacher, n=1)
        self.client.force_login(self.student)

    def test_logged_in_student_play_is_linked_and_tracked(self):
        self.host = self.client.__class__()
        self.host.force_login(self.teacher)
        resp = self.host.post(reverse("start_quiz", args=[self.module.id]))
        session = QuizSession.objects.get(module=self.module)
        self.host.post(reverse("host_start_question", args=[session.code]))
        session.refresh_from_db()

        # student joins logged-in -> participant.user linked
        self.client.post(reverse("join"), {"code": session.code}, follow=True)
        self.client.post(
            reverse("join_name", args=[session.code]),
            {"name": "progresskid"},
            follow=True,
        )
        part = Participant.objects.get(session=session)
        self.assertEqual(part.user, self.student)

        q = session.current_question
        self.client.post(
            reverse("submit_answer", args=[session.code]),
            {"choice_id": q.choices.get(is_correct=True).id},
        )

        # end the quiz
        session.status = QuizSession.Status.ENDED
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at"])

        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn(self.module.title, html)  # module appears in progress
        self.assertIn("Quizzes played", html)

    def test_student_dashboard_empty_state(self):
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(
            resp, "No quizzes yet", status_code=200
        )