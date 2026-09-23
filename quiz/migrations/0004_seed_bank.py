from django.db import migrations

SEED = [
    {
        "subject": "Science",
        "text": "Which planet is known as the Red Planet?",
        "choices": [("Venus", False), ("Mars", True), ("Jupiter", False), ("Saturn", False)],
    },
    {
        "subject": "Science",
        "text": "What gas do plants absorb from the air for photosynthesis?",
        "choices": [("Oxygen", False), ("Nitrogen", False), ("Carbon dioxide", True), ("Hydrogen", False)],
    },
    {
        "subject": "Science",
        "text": "What is the chemical symbol for water?",
        "choices": [("H2O", True), ("CO2", False), ("O2", False), ("NaCl", False)],
    },
    {
        "subject": "Math",
        "text": "What is the value of pi to two decimal places?",
        "choices": [("3.12", False), ("3.14", True), ("3.16", False), ("3.18", False)],
    },
    {
        "subject": "Math",
        "text": "What is 12 × 8?",
        "choices": [("92", False), ("96", True), ("98", False), ("104", False)],
    },
    {
        "subject": "Math",
        "text": "Which number is a prime number?",
        "choices": [("9", False), ("15", False), ("17", True), ("21", False)],
    },
    {
        "subject": "Geography",
        "text": "What is the capital of Japan?",
        "choices": [("Beijing", False), ("Seoul", False), ("Tokyo", True), ("Bangkok", False)],
    },
    {
        "subject": "Geography",
        "text": "Which is the largest ocean on Earth?",
        "choices": [("Atlantic", False), ("Indian", False), ("Arctic", False), ("Pacific", True)],
    },
    {
        "subject": "History",
        "text": "In which year did World War II end?",
        "choices": [("1918", False), ("1939", False), ("1945", True), ("1950", False)],
    },
    {
        "subject": "English",
        "text": "Choose the correct plural of 'child'.",
        "choices": [("Childs", False), ("Children", True), ("Childes", False), ("Children", False)],
    },
    {
        "subject": "ICT",
        "text": "What does 'HTML' stand for?",
        "choices": [
            ("HyperText Markup Language", True),
            ("HighText Machine Language", False),
            ("HyperTransfer Markup Language", False),
            ("None of these", False),
        ],
    },
]


def add_seed(apps, schema_editor):
    BankQuestion = apps.get_model("quiz", "BankQuestion")
    BankChoice = apps.get_model("quiz", "BankChoice")
    for item in SEED:
        bq = BankQuestion.objects.create(
            text=item["text"], subject=item["subject"]
        )
        for order, (text, is_correct) in enumerate(item["choices"], start=1):
            BankChoice.objects.create(
                question=bq, text=text, is_correct=is_correct, order=order
            )


def remove_seed(apps, schema_editor):
    BankQuestion = apps.get_model("quiz", "BankQuestion")
    BankQuestion.objects.filter(
        text__in=[item["text"] for item in SEED]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [("quiz", "0003_alter_activitylog_action_bankquestion_bankchoice")]

    operations = [migrations.RunPython(add_seed, remove_seed)]