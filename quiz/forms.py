from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

from .models import Choice, Module, Question, QuizSession, User


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "email", "role", "password1", "password2"]

    role = forms.ChoiceField(
        choices=[("", "--- Choose a role ---"), *User.Role.choices],
        required=True,
        initial="",
        help_text="Teachers create modules and host quizzes. Students join quizzes with a code.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].widget.attrs = {
            "class": "w-full rounded-md border border-[#d6d6d6] bg-white px-4 py-3 text-sm outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]"
        }
        for name, field in self.fields.items():
            if hasattr(field.widget, "render"):
                field.widget.attrs.update(
                    {
                        "class": "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-sm outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]"
                    }
                )


class LoginForm(AuthenticationForm):
    pass


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ["title", "description"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-sm outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]",
                    "placeholder": "e.g. Networking Fundamentals",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-sm outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]",
                    "rows": 3,
                    "placeholder": "Optional description of the module",
                }
            ),
        }


class QuestionForm(forms.ModelForm):
    choice_1 = forms.CharField(
        label="Choice A",
        max_length=500,
        required=False,
    )
    choice_2 = forms.CharField(
        label="Choice B",
        max_length=500,
        required=False,
    )
    choice_3 = forms.CharField(
        label="Choice C",
        max_length=500,
        required=False,
    )
    choice_4 = forms.CharField(
        label="Choice D",
        max_length=500,
        required=False,
    )
    correct_choice = forms.ChoiceField(
        label="Correct answer",
        choices=[("1", "A"), ("2", "B"), ("3", "C"), ("4", "D")],
        initial="1",
    )

    class Meta:
        model = Question
        fields = ["text", "time_limit", "points"]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "class": "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-sm outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]",
                    "rows": 3,
                    "placeholder": "Type your question here...",
                }
            ),
            "time_limit": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-sm outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]",
                    "min": 5,
                    "max": 300,
                }
            ),
            "points": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-sm outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]",
                    "min": 0,
                }
            ),
        }

    CHOICE_CLASS = "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-sm outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]"

    def __init__(self, *args, **kwargs):
        self.question = kwargs.pop("question", None)
        super().__init__(*args, **kwargs)
        if self.question:
            choices = list(self.question.choices.all())
            for i in range(4):
                if i < len(choices):
                    self.fields[f"choice_{i + 1}"].initial = choices[i].text
            for idx, c in enumerate(choices):
                if c.is_correct:
                    self.fields["correct_choice"].initial = str(idx + 1)
        for name in ["choice_1", "choice_2", "choice_3", "choice_4"]:
            self.fields[name].widget.attrs.update({"class": self.CHOICE_CLASS})

    def clean(self):
        cleaned = super().clean()
        choices = [cleaned.get(f"choice_{i}") for i in range(1, 5)]
        filled = [c for c in choices if c and c.strip()]
        if len(filled) < 2:
            raise forms.ValidationError("You need at least 2 choices (A and B).")
        return cleaned

    def _choice_texts(self):
        cleaned = self.cleaned_data
        return [cleaned.get(f"choice_{i}") for i in range(1, 5)]

    def save_choices(self, question):
        texts = self._choice_texts()
        correct_idx = int(self.cleaned_data.get("correct_choice")) - 1
        question.choices.all().delete()
        for i, text in enumerate(texts):
            if text and text.strip():
                Choice.objects.create(
                    question=question,
                    text=text.strip(),
                    is_correct=(i == correct_idx),
                    order=i + 1,
                )


INPUT_CLASS = "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-sm outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]"


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
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
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Your first name"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Your last name"}
            ),
            "email": forms.EmailInput(
                attrs={"class": INPUT_CLASS, "placeholder": "you@example.com"}
            ),
            "phone": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "+255 000 000 000"}
            ),
            "whatsapp": forms.TextInput(
                attrs={"class": INPUT_CLASS, "style": "padding-left: 2.75rem", "placeholder": "e.g. https://wa.me/255700000000"}
            ),
            "telegram": forms.TextInput(
                attrs={"class": INPUT_CLASS, "style": "padding-left: 2.75rem", "placeholder": "e.g. https://t.me/yourname"}
            ),
            "facebook": forms.TextInput(
                attrs={"class": INPUT_CLASS, "style": "padding-left: 2.75rem", "placeholder": "e.g. https://facebook.com/yourname"}
            ),
            "instagram": forms.TextInput(
                attrs={"class": INPUT_CLASS, "style": "padding-left: 2.75rem", "placeholder": "e.g. https://instagram.com/yourname"}
            ),
            "youtube": forms.TextInput(
                attrs={"class": INPUT_CLASS, "style": "padding-left: 2.75rem", "placeholder": "e.g. https://youtube.com/@yourname"}
            ),
            "tiktok": forms.TextInput(
                attrs={"class": INPUT_CLASS, "style": "padding-left: 2.75rem", "placeholder": "e.g. https://tiktok.com/@yourname"}
            ),
            "website": forms.TextInput(
                attrs={"class": INPUT_CLASS, "style": "padding-left: 2.75rem", "placeholder": "e.g. https://yourschool.ac.tz"}
            ),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if (
            email
            and User.objects.filter(email__iexact=email)
            .exclude(pk=self.instance.pk if self.instance else None)
            .exists()
        ):
            raise forms.ValidationError("That email is already used by another account.")
        return email


class ProfilePasswordForm(forms.Form):
    old_password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "current-password"}),
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_old_password(self):
        old = self.cleaned_data.get("old_password")
        if self.user and not self.user.check_password(old):
            raise forms.ValidationError("Your current password is incorrect.")
        return old

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p1 != p2:
            raise forms.ValidationError("The two password fields don't match.")
        if p1 and self.user and self.user.check_password(p1):
            raise forms.ValidationError("The new password must be different from your current one.")
        return cleaned


class JoinForm(forms.Form):
    code = forms.CharField(
        label="Quiz code",
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-center text-xl font-bold uppercase tracking-[0.4em] outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]",
                "placeholder": "ABC123",
                "maxlength": "6",
                "autocomplete": "off",
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        self.session = QuizSession.objects.filter(code=code).exclude(
            status=QuizSession.Status.ENDED
        ).first()
        if not self.session:
            raise forms.ValidationError("No live quiz found with that code.")
        if self.session.status == QuizSession.Status.ENDED:
            raise forms.ValidationError("That quiz has already ended.")
        return code


class JoinNameForm(forms.Form):
    name = forms.CharField(
        label="Your nickname",
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-md border border-[#d6d6d6] px-4 py-3 text-center text-xl font-bold outline-none focus:border-[#0067c0] focus:ring-2 focus:ring-[#b7d8ff]",
                "placeholder": "Enter your name",
            }
        ),
    )