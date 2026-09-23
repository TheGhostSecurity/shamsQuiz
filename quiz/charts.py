import base64
import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#e7e7e7",
        "axes.labelcolor": "#424242",
        "text.color": "#1f1f1f",
        "xtick.color": "#8c8c8c",
        "ytick.color": "#8c8c8c",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 11,
    }
)

BRAND = "#0067c0"
LIGHT = "#37a5ff"
PALE = "#b7d8ff"
AMBER = "#d99322"
GREEN = "#107c41"
RED = "#dc2626"
NAVY = "#002b3f"
GREY = "#a3a3a3"


def _data_uri(fig):
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=140, bbox_inches="tight", facecolor="white"
    )
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode()


def score_trend(labels, values):
    if not labels:
        return None
    fig, ax = plt.subplots(figsize=(8.4, 3.2))
    xs = range(len(values))
    ax.plot(
        xs,
        values,
        color=BRAND,
        linewidth=2.5,
        marker="o",
        markersize=6,
        markerfacecolor="white",
        markeredgewidth=2,
        markeredgecolor=BRAND,
        zorder=3,
    )
    ax.fill_between(xs, values, color=LIGHT, alpha=0.15, zorder=1)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, rotation=28, ha="right", fontsize=9)
    ax.grid(axis="y", color="#efefef", linewidth=1)
    ax.set_ylim(bottom=0)
    ax.set_title("Average score per ended quiz", fontsize=13, fontweight="bold", color=NAVY, loc="left", pad=14)
    ax.set_ylabel("Avg score")
    return _data_uri(fig)


def participation_chart(labels, values):
    if not labels:
        return None
    fig, ax = plt.subplots(figsize=(8.4, 3.2))
    xs = range(len(values))
    bars = ax.bar(xs, values, color=PALE, edgecolor=BRAND, linewidth=0.6, zorder=2)
    for x, v in zip(xs, values):
        ax.text(x, v + 0.15, str(v), ha="center", fontsize=10, fontweight="bold", color=NAVY)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, rotation=28, ha="right", fontsize=9)
    ax.grid(axis="y", color="#efefef", linewidth=1)
    ax.set_ylim(bottom=0)
    ax.set_title("Players per quiz", fontsize=13, fontweight="bold", color=NAVY, loc="left", pad=14)
    ax.set_ylabel("Players")
    return _data_uri(fig)


def accuracy_donut(correct, wrong):
    total = correct + wrong
    if total == 0:
        return None
    fig, ax = plt.subplots(figsize=(3.2, 3.2))
    ax.pie(
        [correct, wrong],
        colors=[GREEN, RED],
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.42, edgecolor="white"),
    )
    pct = round(correct / total * 100)
    ax.text(
        0, 0, f"{pct}%", ha="center", va="center",
        fontsize=22, fontweight="bold", color=GREEN,
    )
    ax.text(
        0, -0.28, "correct", ha="center", va="center",
        fontsize=10, color="#8c8c8c",
    )
    ax.legend(
        [f"Correct ({correct})", f"Wrong ({wrong})"],
        loc="lower center", bbox_to_anchor=(0.5, -0.28), ncol=2, frameon=False, fontsize=9,
    )
    return _data_uri(fig)


def leaderboard_chart(names, scores):
    if not names:
        return None
    data = sorted(zip(names, scores), key=lambda t: t[1], reverse=True)
    names, scores = zip(*data)
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    ys = range(len(names))
    colors = [AMBER if i == 0 else (BRAND if i < 3 else PALE) for i in ys]
    ax.barh(list(ys), scores, color=colors, edgecolor="#c8c8c8", linewidth=0.4, height=0.62, zorder=2)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(names, fontsize=9.5)
    ax.invert_yaxis()
    for y, v in zip(ys, scores):
        ax.text(v + (max(scores) * 0.01) if max(scores) else 1, y, str(v), va="center", fontsize=9, fontweight="bold", color=NAVY)
    ax.grid(axis="x", color="#efefef", linewidth=1)
    ax.set_xlim(0, max(scores) * 1.12 if max(scores) else 10)
    ax.set_title("Final scores", fontsize=13, fontweight="bold", color=NAVY, loc="left", pad=12)
    ax.set_xlabel("Points")
    return _data_uri(fig)


def leaderboard_png(names, scores):
    if not names:
        return None
    data = sorted(zip(names, scores), key=lambda t: t[1], reverse=True)
    names, scores = zip(*data)
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ys = range(len(names))
    colors = [AMBER if i == 0 else (BRAND if i < 3 else PALE) for i in ys]
    ax.barh(list(ys), scores, color=colors, edgecolor="#c8c8c8", linewidth=0.4, height=0.62, zorder=2)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(names, fontsize=9.5)
    ax.invert_yaxis()
    for y, v in zip(ys, scores):
        ax.text(v + (max(scores) * 0.01) if max(scores) else 1, y, str(v), va="center", fontsize=9, fontweight="bold", color=NAVY)
    ax.grid(axis="x", color="#efefef", linewidth=1)
    ax.set_xlim(0, max(scores) * 1.12 if max(scores) else 10)
    ax.set_title(f"Final scores · {len(scores)} players", fontsize=13, fontweight="bold", color=NAVY, loc="left", pad=12)
    ax.set_xlabel("Points")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()