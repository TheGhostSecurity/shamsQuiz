from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from quiz.models import (
    Answer,
    Choice,
    Module,
    Participant,
    Question,
    QuizSession,
    TeacherUtil,
    User,
)

from .permissions import hash_ticket

STRONG_PW = "Quizpass123!"


def make_teacher(username="teacher1"):
    return User.objects.create_user(
        username=username, password=STRONG_PW, role="teacher"
    )


def make_student(username="student1", password=STRONG_PW):
    return User.objects.create_user(
        username=username, password=password, role="student"
    )


def make_module(teacher, n=2):
    module = Module.objects.create(title="Module X", teacher=teacher)
    for i in range(n):
        question = Question.objects.create(
            module=module, text=f"Question {i + 1}", time_limit=30
        )
        Choice.objects.create(question=question, text="Right", is_correct=True, order=1)
        Choice.objects.create(question=question, text="Wrong A", order=2)
        Choice.objects.create(question=question, text="Wrong B", order=3)
    return module


def make_session(teacher, module=None, status=QuizSession.Status.WAITING, code=None):
    module = module or make_module(teacher)
    return QuizSession.objects.create(
        module=module, host=teacher, status=status, code=code or "ABC123"
    )


def authed(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class AuthTests(APITestCase):
    def test_register_returns_tokens_and_user(self):
        resp = self.client.post(
            reverse("mobileapi:register"),
            {
                "username": "amina",
                "password": STRONG_PW,
                "password_confirm": STRONG_PW,
                "first_name": "Amina",
                "email": "amina@example.com",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertIn("access", body["tokens"])
        self.assertIn("refresh", body["tokens"])
        self.assertEqual(body["user"]["username"], "amina")
        self.assertEqual(body["user"]["role"], "student")
        self.assertEqual(body["user"]["display_name"], "Amina")
        self.assertTrue(User.objects.filter(username="amina").exists())

    def test_register_rejects_duplicate_username(self):
        make_student("amina")
        resp = self.client.post(
            reverse("mobileapi:register"),
            {
                "username": "amina",
                "password": STRONG_PW,
                "password_confirm": STRONG_PW,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("username", resp.json()["fields"])

    def test_register_rejects_password_mismatch(self):
        resp = self.client.post(
            reverse("mobileapi:register"),
            {
                "username": "amina",
                "password": STRONG_PW,
                "password_confirm": "Different123!",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password_confirm", resp.json()["fields"])

    def test_register_rejects_weak_password(self):
        resp = self.client.post(
            reverse("mobileapi:register"),
            {
                "username": "amina",
                "password": "123",
                "password_confirm": "123",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_login_with_username(self):
        make_student("amina")
        resp = self.client.post(
            reverse("mobileapi:login"),
            {"username": "amina", "password": STRONG_PW},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json()["tokens"])

    def test_login_with_email(self):
        user = make_student("amina")
        user.email = "amina@example.com"
        user.save()
        resp = self.client.post(
            reverse("mobileapi:login"),
            {"username": "amina@example.com", "password": STRONG_PW},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_login_rejects_wrong_password(self):
        make_student("amina")
        resp = self.client.post(
            reverse("mobileapi:login"),
            {"username": "amina", "password": "nope"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])

    def test_login_rejects_archived_account(self):
        user = make_student("amina")
        user.archive()
        resp = self.client.post(
            reverse("mobileapi:login"),
            {"username": "amina", "password": STRONG_PW},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_me_requires_authentication(self):
        resp = self.client.get(reverse("mobileapi:me"))
        self.assertEqual(resp.status_code, 401)

    def test_me_returns_profile(self):
        user = make_student("amina")
        user.first_name = "Amina"
        user.save()
        resp = authed(user).get(reverse("mobileapi:me"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user"]["display_name"], "Amina")

    def test_me_patch_updates_profile(self):
        user = make_student("amina")
        resp = authed(user).patch(
            reverse("mobileapi:me"),
            {"phone": "+255700000000", "email": "new@example.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.phone, "+255700000000")
        self.assertEqual(user.email, "new@example.com")

    def test_me_patch_rejects_duplicate_email(self):
        make_student("other", password=STRONG_PW)
        other = User.objects.get(username="other")
        other.email = "taken@example.com"
        other.save()
        user = make_student("amina")
        resp = authed(user).patch(
            reverse("mobileapi:me"), {"email": "taken@example.com"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("email", resp.json()["fields"])

    def test_password_change(self):
        user = make_student("amina")
        resp = authed(user).post(
            reverse("mobileapi:change-password"),
            {"current_password": STRONG_PW, "new_password": "Brandnew456!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("Brandnew456!"))

    def test_password_change_wrong_current(self):
        user = make_student("amina")
        resp = authed(user).post(
            reverse("mobileapi:change-password"),
            {"current_password": "wrong", "new_password": "Brandnew456!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class JoinAndPlayTests(APITestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.module = make_module(self.teacher, n=2)
        self.session = make_session(self.teacher, self.module)
        self.student = make_student("amina")

    def start_question(self, session=None):
        session = session or self.session
        session.status = QuizSession.Status.QUESTION
        session.current_index = 0
        session.question_started_at = timezone.now()
        session.question_ends_at = timezone.now() + timedelta(seconds=30)
        session.save()
        return session

    def test_join_creates_participant_and_ticket(self):
        resp = authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": self.session.code, "nickname": "Amina"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ticket"])
        participant = Participant.objects.get(session=self.session, name="Amina")
        self.assertEqual(participant.user, self.student)
        self.assertEqual(participant.api_token, hash_ticket(body["ticket"]))

    def test_join_accepts_lowercase_code(self):
        resp = authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": "abc123", "nickname": "Amina"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_join_unknown_code(self):
        resp = authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": "ZZZ999", "nickname": "Amina"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("code", resp.json()["fields"])

    def test_join_ended_session_rejected(self):
        self.session.status = QuizSession.Status.ENDED
        self.session.save()
        resp = authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": self.session.code, "nickname": "Amina"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_join_duplicate_name_rejected(self):
        Participant.objects.create(session=self.session, name="Amina")
        resp = authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": self.session.code, "nickname": "Amina"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("nickname", resp.json()["fields"])

    def test_join_short_name_rejected(self):
        resp = authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": self.session.code, "nickname": "A"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_join_requires_team_when_teams_enabled(self):
        self.session.teams_enabled = True
        self.session.save()
        resp = authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": self.session.code, "nickname": "Amina"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("team", resp.json()["fields"])

    def test_join_with_team_succeeds(self):
        self.session.teams_enabled = True
        self.session.save()
        resp = authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": self.session.code, "nickname": "Amina", "team": "red"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        participant = Participant.objects.get(session=self.session, name="Amina")
        self.assertEqual(participant.team, "red")

    def test_join_twice_reuses_participant(self):
        authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": self.session.code, "nickname": "Amina"},
            format="json",
        )
        authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": self.session.code, "nickname": "Amina"},
            format="json",
        )
        self.assertEqual(
            Participant.objects.filter(session=self.session, name="Amina").count(), 1
        )

    def test_answer_correct_awards_full_points(self):
        self.start_question()
        ticket = self._join()
        question = self.session.current_question
        correct = question.choices.filter(is_correct=True).first()
        resp = self._answer(ticket, correct.id)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["result"]["correct"])
        self.assertGreater(body["result"]["points"], 900)
        participant = Participant.objects.get(session=self.session, name="Amina")
        self.assertEqual(participant.score, body["result"]["points"])

    def test_answer_wrong_awards_zero(self):
        self.start_question()
        ticket = self._join()
        question = self.session.current_question
        wrong = question.choices.filter(is_correct=False).first()
        resp = self._answer(ticket, wrong.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["result"]["points"], 0)

    def test_answer_twice_rejected(self):
        self.start_question()
        ticket = self._join()
        question = self.session.current_question
        correct = question.choices.filter(is_correct=True).first()
        self._answer(ticket, correct.id)
        resp = self._answer(ticket, correct.id)
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(resp.json()["ok"])

    def test_answer_invalid_choice_rejected(self):
        self.start_question()
        ticket = self._join()
        resp = self._answer(ticket, 999999)
        self.assertEqual(resp.status_code, 400)

    def test_answer_without_ticket_rejected(self):
        self.start_question()
        client = APIClient()
        resp = client.post(
            reverse("mobileapi:answer", args=[self.session.code]),
            {"choice_id": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_answer_when_not_accepting_rejected(self):
        self.session.status = QuizSession.Status.REVEAL
        self.session.save()
        ticket = self._join()
        question = self.session.current_question
        correct = question.choices.filter(is_correct=True).first()
        resp = self._answer(ticket, correct.id)
        self.assertEqual(resp.status_code, 400)

    def test_state_shuffles_choices_consistently(self):
        self.start_question()
        ticket = self._join()
        first = self._state(ticket)
        second = self._state(ticket)
        self.assertEqual(
            [c["id"] for c in first["question"]["choices"]],
            [c["id"] for c in second["question"]["choices"]],
        )

    def test_state_hides_correct_answer_before_reveal(self):
        self.start_question()
        ticket = self._join()
        state = self._state(ticket)
        for choice in state["question"]["choices"]:
            self.assertIsNone(choice["is_correct"])

    def test_state_reveals_correct_answer_after_reveal(self):
        self.start_question()
        ticket = self._join()
        self.session.status = QuizSession.Status.REVEAL
        self.session.save()
        state = self._state(ticket)
        flags = [c["is_correct"] for c in state["question"]["choices"]]
        self.assertIn(True, flags)

    def test_state_includes_my_answer(self):
        self.start_question()
        ticket = self._join()
        question = self.session.current_question
        correct = question.choices.filter(is_correct=True).first()
        self._answer(ticket, correct.id)
        state = self._state(ticket)
        self.assertTrue(state["participant"]["has_answered"])
        self.assertEqual(state["my_answer"]["choice_id"], correct.id)
        self.assertTrue(state["my_answer"]["correct"])

    def test_state_reports_joined_false_without_identity(self):
        self.start_question()
        resp = APIClient().get(
            reverse("mobileapi:state", args=[self.session.code])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["joined"])

    def test_timer_expiry_moves_session_to_reveal(self):
        self.start_question()
        self.session.question_ends_at = timezone.now() - timedelta(seconds=1)
        self.session.save()
        ticket = self._join()
        state = self._state(ticket)
        self.assertEqual(state["status"], QuizSession.Status.REVEAL)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, QuizSession.Status.REVEAL)

    def test_scoreboard_ranks_by_score(self):
        self.start_question()
        ticket = self._join()
        question = self.session.current_question
        correct = question.choices.filter(is_correct=True).first()
        self._answer(ticket, correct.id)
        resp = authed(self.student).get(
            reverse("mobileapi:scoreboard", args=[self.session.code])
        )
        self.assertEqual(resp.status_code, 200)
        board = resp.json()["leaderboard"]
        self.assertEqual(board[0]["name"], "Amina")
        self.assertEqual(board[0]["rank"], 1)

    def _join(self):
        resp = authed(self.student).post(
            reverse("mobileapi:join"),
            {"code": self.session.code, "nickname": "Amina"},
            format="json",
        )
        return resp.json()["ticket"]

    def _answer(self, ticket, choice_id):
        client = APIClient()
        client.credentials(HTTP_X_QUIZ_TICKET=ticket)
        return client.post(
            reverse("mobileapi:answer", args=[self.session.code]),
            {"choice_id": choice_id},
            format="json",
        )

    def _state(self, ticket):
        client = APIClient()
        client.credentials(HTTP_X_QUIZ_TICKET=ticket)
        resp = client.get(reverse("mobileapi:state", args=[self.session.code]))
        return resp.json()["state"]


class StudentFeedTests(APITestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.module = make_module(self.teacher, n=2)
        self.student = make_student("amina")

    def test_home_returns_stats_and_recent_sessions(self):
        session = make_session(self.teacher, self.module)
        participant = Participant.objects.create(
            session=session, name="Amina", user=self.student, score=1500
        )
        resp = authed(self.student).get(reverse("mobileapi:home"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["stats"]["quizzes_played"], 1)
        self.assertEqual(body["stats"]["best_score"], 1500)
        self.assertEqual(len(body["my_sessions"]), 1)
        self.assertEqual(body["my_sessions"][0]["code"], session.code)
        self.assertEqual(participant.session.code, session.code)

    def test_home_lists_live_quizzes(self):
        make_session(self.teacher, self.module, status=QuizSession.Status.WAITING)
        resp = authed(self.student).get(reverse("mobileapi:home"))
        self.assertEqual(len(resp.json()["live_quizzes"]), 1)

    def test_modules_lists_modules_with_counts(self):
        resp = authed(self.student).get(reverse("mobileapi:modules"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 1)
        self.assertEqual(resp.json()["modules"][0]["question_count"], 2)

    def test_modules_blocked_for_teacher(self):
        resp = authed(self.teacher).get(reverse("mobileapi:modules"))
        self.assertEqual(resp.status_code, 403)

    def test_progress_available_for_student(self):
        resp = authed(self.student).get(reverse("mobileapi:progress"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["stats"]["quizzes_joined"], 0)
        self.assertEqual(body["stats"]["accuracy"], 0)
        for key in ("stats", "modules", "history", "trend"):
            self.assertIn(key, body)

    def test_progress_payload_is_json_safe(self):
        session = make_session(self.teacher, self.module)
        session.status = QuizSession.Status.ENDED
        from django.utils import timezone as tz

        session.ended_at = tz.now()
        session.save()
        participant = Participant.objects.create(
            session=session, name="Amina", user=self.student, score=1500
        )
        question = session.current_question
        correct = question.choices.filter(is_correct=True).first()
        Answer.objects.create(
            participant=participant, question=question, choice=correct, points_earned=1000
        )
        resp = authed(self.student).get(reverse("mobileapi:progress"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        stats = body["stats"]
        self.assertEqual(stats["quizzes_ended"], 1)
        self.assertEqual(stats["total_points"], 1500)
        self.assertEqual(stats["best_score"], 1500)
        self.assertEqual(stats["accuracy"], 100)
        self.assertEqual(len(body["history"]), 1)
        row = body["history"][0]
        self.assertEqual(row["score"], 1500)
        self.assertEqual(row["rank"], 1)
        self.assertIsInstance(row["played_at"], str)
        self.assertEqual(len(body["modules"]), 1)
        self.assertEqual(body["modules"][0]["quizzes"], 1)
        self.assertNotIn("trend_chart", body)
        self.assertEqual(len(body["trend"]), 1)

    def test_progress_blocked_for_teacher(self):
        resp = authed(self.teacher).get(reverse("mobileapi:progress"))
        self.assertEqual(resp.status_code, 403)

    def test_utils_lists_teacher_files(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        TeacherUtil.objects.create(
            teacher=self.teacher,
            title="Notes",
            category="book",
            file=SimpleUploadedFile("notes.pdf", b"%PDF-1.4"),
        )
        resp = authed(self.student).get(reverse("mobileapi:utils"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["teachers"]), 1)
        self.assertEqual(body["teachers"][0]["name"], "teacher1")
        self.assertEqual(len(body["files"]), 1)
        self.assertEqual(body["files"][0]["title"], "Notes")
        self.assertTrue(body["files"][0]["file_url"].startswith("http"))
