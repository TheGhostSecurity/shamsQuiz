import io
import os
import tempfile

from django.db.models import Avg, Count
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .charts import leaderboard_png
from .models import Answer

NAVY = colors.HexColor("#002b3f")
BRAND = colors.HexColor("#0067c0")
PALE = colors.HexColor("#eaf4ff")
GREEN = colors.HexColor("#107c41")
RED = colors.HexColor("#dc2626")
GREY = colors.HexColor("#5c5c5c")
BORDER = colors.HexColor("#e0e0e0")


def _style():
    return ParagraphStyle


def _title():
    return ParagraphStyle(
        "Title",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=NAVY,
    )


def _subtitle():
    return ParagraphStyle(
        "Subtitle",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=GREY,
    )


def _section():
    return ParagraphStyle(
        "Section",
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=BRAND,
        spaceBefore=14,
        spaceAfter=8,
    )


def _chart_flowable(png_bytes, max_w=150 * mm, max_h=70 * mm, cleanup=None):
    if not png_bytes:
        return None
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    f.write(png_bytes)
    f.close()
    cleanup.append(f.name)
    iw, ih = ImageReader(f.name).getSize()
    scale = min(max_w / iw, max_h / ih)
    return Image(f.name, width=iw * scale, height=ih * scale)


def _table(data, col_widths=None, aligns=None):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if aligns:
        for col, a in aligns.items():
            style.append(("ALIGN", (col, 0), (col, -1), a))
    t.setStyle(TableStyle(style))
    return t


def build_session_report(session, leaderboard):
    answers = list(
        Answer.objects.filter(participant__session=session)
        .select_related("participant", "question", "choice")
    )
    cleanup = []
    correct = sum(1 for a in answers if a.choice.is_correct)
    total = len(answers)
    accuracy = round(correct / total * 100) if total else 0
    avg_score = (
        round(sum(p.score for p in leaderboard) / len(leaderboard)) if leaderboard else 0
    )
    top = leaderboard[0] if leaderboard else None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"ShamsQuiz report · {session.code}",
        author="ShamsQuiz",
    )

    story = []
    story.append(Paragraph("ShamsQuiz", _subtitle()))
    story.append(Paragraph("Quiz Report", _title()))
    story.append(Spacer(1, 6))

    info = _table(
        [
            ["Module", "Code", "Host", "Played on"],
            [
                session.module.title,
                session.code,
                session.host.username,
                (session.ended_at or session.created_at).strftime("%b %d, %Y · %H:%M"),
            ],
        ],
        col_widths=[70 * mm, 22 * mm, 32 * mm, 32 * mm],
    )
    story.append(info)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Summary", _section()))
    summary = _table(
        [
            ["Players", "Answers", "Correct", "Accuracy", "Avg score", "Top score"],
            [
                str(len(leaderboard)),
                str(total),
                str(correct),
                f"{accuracy}%",
                str(avg_score),
                str(top.score if top else "—"),
            ],
        ],
        col_widths=[22 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm],
        aligns={1: "CENTER", 2: "CENTER", 3: "CENTER", 4: "CENTER", 5: "CENTER"},
    )
    story.append(summary)
    story.append(Spacer(1, 10))

    if top:
        story.append(
            Paragraph(
                f'<font color="#d99322">Winner:</font> {top.name} with '
                f"{top.score} points",
                ParagraphStyle(
                    "Winner",
                    fontName="Helvetica-Bold",
                    fontSize=11,
                    leading=15,
                    textColor=NAVY,
                ),
            )
        )
        story.append(Spacer(1, 6))

    story.append(Paragraph("Final scores", _section()))
    if leaderboard:
        lb_data = [["Rank", "Player", "Score"]] + [
            [f"#{i + 1}", name, score]
            for i, (name, score) in enumerate(
                (p.name, p.score) for p in leaderboard
            )
        ]
        story.append(
            _table(
                lb_data,
                col_widths=[18 * mm, 110 * mm, 28 * mm],
                aligns={2: "CENTER"},
            )
        )
        story.append(Spacer(1, 8))
        chart = _chart_flowable(
            leaderboard_png(
                [p.name for p in leaderboard],
                [p.score for p in leaderboard],
            ),
            cleanup=cleanup,
        )
        if chart:
            story.append(chart)
    else:
        story.append(Paragraph("No players joined this quiz.", _subtitle()))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Question performance", _section()))
    questions = list(session.module.questions.all())
    if questions and answers:
        q_data = [["#", "Question", "Correct", "Wrong", "Books"]]
        for i, q in enumerate(questions, start=1):
            q_answers = [a for a in answers if a.question_id == q.id]
            q_correct = sum(1 for a in q_answers if a.choice.is_correct)
            q_wrong = len(q_answers) - q_correct
            q_data.append(
                [
                    str(i),
                    q.text,
                    str(q_correct),
                    str(q_wrong),
                    str(len(q_answers)),
                ]
            )
        story.append(
            _table(
                q_data,
                col_widths=[10 * mm, 100 * mm, 20 * mm, 20 * mm, 16 * mm],
                aligns={2: "CENTER", 3: "CENTER", 4: "CENTER"},
            )
        )
    else:
        story.append(Paragraph("No answers recorded.", _subtitle()))

    doc.build(story)
    for path in cleanup:
        try:
            os.unlink(path)
        except OSError:
            pass
    buf.seek(0)
    return buf.read()