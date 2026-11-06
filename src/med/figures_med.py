"""Figures for docs/CHRONOMED.md (matplotlib, global Python; reads only data/med/results/*.json).

  python -I src/med/figures_med.py   -> data/med/figures/*.png (200 dpi) + data/med/results/figures_data.json
Style: white background, one message per figure, one y-axis, two categorical hues (tax = blue, health = orange,
validated for colour-vision deficiency), ordinal blue ramp for versions in time, hairline grid, direct labels.
"""
import os
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
RES = ROOT / "data" / "med" / "results"
FIGS = ROOT / "data" / "med" / "figures"
APPLICANT = Path(os.environ["FIG_COPY_DIR"]) if os.environ.get("FIG_COPY_DIR") else None  # optional extra copy
TAX, MED = "#2a78d6", "#eb6834"            # categorical slots 1-2 (validated on #ffffff)
OLD, NEW = "#86b6ef", "#256abf"            # ordinal ramp steps 250 / 500 (validated, --ordinal)
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
WINDOW = "#d9d8d2"                          # "promulgated, not yet in force" (neutral gray, labelled)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK, "figure.facecolor": "white",
                     "axes.facecolor": "white", "savefig.facecolor": "white"})


def load(name):
    return json.loads((RES / name).read_text(encoding="utf-8"))


def style(ax, grid_axis="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def bar(ax, x, h, w, color, horizontal=False):
    """Thin bar from a single baseline (no outline)."""
    if horizontal:
        ax.barh(x, h, height=w, color=color, edgecolor="none")
    else:
        ax.bar(x, h, width=w, color=color, edgecolor="none")


def fig1(rr, out):
    """Wrong version @1 by index, tax vs health; amount and wording probes as two small multiples."""
    modes = [("static", "Dates\nignored"), ("latest", "Today's\ntext only"), ("temporal", "In force\non the date")]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.9), sharey=True)
    fig.subplots_adjust(top=0.74, wspace=0.12)
    data = {}
    for ax, (ptype, title) in zip(axes, (("amount", "Amount probes"), ("span", "Changed-wording probes"))):
        t, m = rr[f"tax_{ptype}"], rr[f"medical_{ptype}"]
        for i, (mode, label) in enumerate(modes):
            for dx, res, col in ((-0.19, t, TAX), (0.19, m, MED)):
                v = res[mode]["wrong_version@1"] * 100
                lo, hi = (c * 100 for c in res[mode]["wrong_version@1_ci"])
                bar(ax, i + dx, v, 0.34, col)
                ax.plot([i + dx, i + dx], [max(lo, 0), hi], color=INK2, lw=1)
                ax.text(i + dx, hi + 1.2, f"{v:.0f}%" if v >= 1 or v == 0 else f"{v:.1f}%", ha="center", va="bottom",
                        fontsize=8, color=INK)
                data[f"{ptype}/{mode}/{'tax' if col == TAX else 'health'}"] = [round(v, 1), round(lo, 1), round(hi, 1)]
        ax.set_xticks(range(3), [lbl for _, lbl in modes])
        ax.set_xlim(-0.6, 2.6)
        ax.set_title(f"{title} (tax n={t['static']['n']:,}, health n={m['static']['n']:,})", fontsize=8.5, loc="left",
                     color=INK2)
        style(ax)
    axes[0].set_ylim(0, 58)
    axes[0].set_ylabel("Right article, wrong version at rank 1 (%)")
    handles = [Rectangle((0, 0), 1, 1, fc=TAX), Rectangle((0, 0), 1, 1, fc=MED)]
    fig.legend(handles, ["Tax law (ChronoTax, 23 acts)", "Health law (ChronoMed, 20 acts)"], loc="upper left",
               frameon=False, ncol=2, bbox_to_anchor=(0.005, 0.905), fontsize=8.5)
    fig.suptitle("Ignoring dates retrieves outdated versions in both domains; the validity filter removes them",
                 x=0.01, ha="left", fontsize=10.5, fontweight="bold", color=INK, y=0.985)
    fig.text(0.01, -0.04, "Whiskers: Wilson 95% CI. Same generator (seed 19) and same retrieval code for both domains.",
             fontsize=7.5, color=MUTED)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return data


def fig2(st, out):
    """Promulgation -> commencement delay of every delayed amendment since 1990, tax vs health (strip plot)."""
    import random
    rng = random.Random(7)
    names = {"02536": "Patient Right to Autonomy Act", "01189": "NHI Act 2011 revision ('2nd-generation NHI')",
             "07121": "Medical Devices Act", "02588": "Long-Term Care Services Act"}
    fig, ax = plt.subplots(figsize=(7.4, 2.9))
    data = {}
    for row, (dom, col, label) in enumerate((("tax", TAX, "Tax law"), ("medical", MED, "Health law"))):
        xs = [e for e in st["history_forms"][dom]["delayed_entries"] if e[2] >= "1990-01-01"]
        ds = sorted(e[4] for e in xs)
        med = ds[len(ds) // 2] if len(ds) % 2 else (ds[len(ds) // 2 - 1] + ds[len(ds) // 2]) / 2
        data[dom] = {"n_delayed_since_1990": len(ds), "median_days": med, "max_days": ds[-1]}
        y = 1 - row
        ax.scatter([e[4] for e in xs], [y + rng.uniform(-0.17, 0.17) for _ in xs], s=26, color=col,
                   edgecolors="white", linewidths=1.2, zorder=3)
        ax.plot([med, med], [y - 0.28, y + 0.28], color=INK, lw=2, zorder=4)
        ax.text(med, y + 0.31, f"median {med:.0f} days", ha="center", va="bottom", fontsize=7.5, color=INK)
        ax.text(2.2, y, f"{label}\n{len(ds)} delayed amendments", ha="right", va="center", fontsize=8.5, color=INK)
        if dom == "medical":
            e = max(xs, key=lambda e: e[4])
            ax.annotate(f"{names.get(e[0], e[0])}: {e[4] / 365.25:.1f} years", (e[4], y - 0.05), xytext=(e[4], y - 0.6),
                        fontsize=7.5, color=INK2, ha="center", va="top",
                        arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.7})
    ax.set_xscale("log")
    ax.set_xlim(2.5, 4000)
    ax.set_ylim(-1.15, 1.6)
    ax.set_yticks([])
    ax.set_xticks([7, 30, 90, 180, 365, 730, 1461], ["1 wk", "1 mo", "3 mo", "6 mo", "1 yr", "2 yr", "4 yr"])
    ax.set_xlabel("Days from promulgation to commencement (log scale; only amendments later than the default "
                  "'third day')", fontsize=8)
    style(ax, grid_axis="x")
    ax.spines["left"].set_visible(False)
    ax.set_title("Health law starts later: when an amendment is delayed, the median wait is months longer",
                 loc="left", fontsize=11, fontweight="bold", color=INK, pad=12)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return data


def fig3(st, out):
    """What changes between consecutive article versions (since 1990): tax vs health."""
    cp = st["change_profile"]
    rows = [("from a whole-act revision\n(articles often renumbered)", "share_from_full_text_revision", None),
            ("with a changed money amount", "with_amount_change", "article_transitions_since_1990"),
            ("with a changed percentage", "with_percentage_change", "article_transitions_since_1990")]
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    data = {}
    for i, (label, key, den) in enumerate(rows):
        for dy, dom, col in ((-0.17, "tax", TAX), (0.17, "medical", MED)):
            v = (cp[dom][key] if den is None else cp[dom][key] / cp[dom][den]) * 100
            bar(ax, i + dy, v, 0.3, col, horizontal=True)
            ax.text(v + 0.8, i + dy, f"{v:.1f}%", va="center", fontsize=8, color=INK)
            data[f"{key}/{dom}"] = round(v, 1)
    ax.set_yticks(range(3), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 64)
    ax.set_ylim(2.6, -0.6)
    ax.set_xlabel(f"Share of article changes since 1990 (tax n={cp['tax']['article_transitions_since_1990']:,}, "
                  f"health n={cp['medical']['article_transitions_since_1990']:,})", fontsize=8)
    style(ax, grid_axis="x")
    handles = [Rectangle((0, 0), 1, 1, fc=TAX), Rectangle((0, 0), 1, 1, fc=MED)]
    ax.legend(handles, ["Tax law", "Health law"], loc="lower right", frameon=False)
    ax.set_title("Health law changes mostly by rewriting whole acts, rarely by changing amounts",
                 loc="left", fontsize=11, fontweight="bold", color=INK, pad=10)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return data


def fig4(ex, out):
    """Three 'same question, two dates' examples as version timelines."""
    d = dt.date.fromisoformat
    spec = {
        "nhi_supplementary_premium": ("NHI Act Art. 31: supplementary premium on a second salary?",
                                      [("1995-03-01", "2013-01-01", OLD, "old Art. 31: no premium"),
                                       ("2013-01-01", "2027-01-01", NEW, "new Art. 31: premium withheld")],
                                      ("2011-01-26", "2013-01-01")),
        "pharma_fine_cap": ("Pharmaceutical Affairs Act Art. 92(1): maximum fine?",
                            [("1993-02-07", "2015-12-04", OLD, "cap NT$150,000"),
                             ("2015-12-04", "2027-01-01", NEW, "cap NT$2,000,000")], None),
        "smoking_age": ("Tobacco Hazards Prevention Act (Art. 12, then Art. 16): may a 19-year-old smoke?",
                        [("2009-01-11", "2023-03-22", OLD, "Art. 12: smoking banned under 18"),
                         ("2023-03-22", "2027-01-01", NEW, "under 20")], ("2023-02-15", "2023-03-22")),
    }
    short = {"nhi_supplementary_premium": {"no such rule in force": "No", True: "Yes"},
             "pharma_fine_cap": {150000: "NT$150,000", 2000000: "NT$2,000,000"},
             "smoking_age": {18: "Yes (ban is under 18)", 20: "No (ban is under 20)"}}
    fig, axes = plt.subplots(3, 1, figsize=(7.4, 5.2), sharex=True)
    data = {}
    for ax, e in zip(axes, ex):
        title, segs, window = spec[e["id"]]
        marks = sorted(d(q) for q in e["by_date"])
        for a, b, col, label in segs:
            ax.barh(0, (d(b) - d(a)).days, left=d(a), height=0.42, color=col, edgecolor="white", linewidth=2)
            # centre the label in the longest stretch of the visible bar that no question-date marker crosses
            lo, hi = max(d(a), dt.date(2008, 6, 1)), min(d(b), dt.date(2027, 1, 1))
            cuts = [lo] + [m for m in marks if lo < m < hi] + [hi]
            pieces = [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]
            p0, p1 = max(pieces, key=lambda p: p[1] - p[0])
            ax.text(p0 + (p1 - p0) / 2, 0, label, ha="center", va="center", fontsize=7.5,
                    color="white" if col == NEW else INK)
        if window:
            ax.barh(-0.42, (d(window[1]) - d(window[0])).days, left=d(window[0]), height=0.16, color=WINDOW)
            ax.text(d(window[0]) - dt.timedelta(days=60), -0.42, "promulgated, not yet in force", ha="right",
                    va="center", fontsize=7, color=INK2)
        for k, (qd, row) in enumerate(e["by_date"].items()):
            ans = short[e["id"]].get(row["answer"], str(row["answer"]))
            ax.plot([d(qd), d(qd)], [-0.62, 0.42], color=INK, lw=1, zorder=4)
            ax.scatter([d(qd)], [0.42], s=30, color=INK, edgecolors="white", linewidths=1.5, zorder=5)
            off = dt.timedelta(days=45)
            ax.text(d(qd) - off if k == 0 else d(qd) + off, 0.6, f"asked {qd}:\n{ans}",
                    ha="right" if k == 0 else "left", va="center", fontsize=7.5, color=INK)
            data[f"{e['id']}/{qd}"] = ans
        ax.set_ylim(-0.75, 1.05)
        ax.set_yticks([])
        ax.set_title(title, loc="left", fontsize=8.5, color=INK2)
        style(ax, grid_axis="x")
        ax.spines["left"].set_visible(False)
    axes[-1].set_xlim(dt.date(2008, 6, 1), dt.date(2027, 1, 1))
    axes[-1].xaxis.set_major_locator(mdates.YearLocator(2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle("Same question, different correct answer depending on the date", x=0.01, ha="left", fontsize=11,
                 fontweight="bold", color=INK, y=1.0)
    fig.text(0.01, -0.02, "Light = before the change, dark = after it (bars start at the commencement date). "
             "Source: ChronoMed store; dates hand-checked against the MOJ amendment history.", fontsize=7, color=MUTED)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return data


def main() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    rr = load("retrieval_side_by_side.json")["results"]
    st = load("store_stats.json")
    ex = load("examples.json")
    data = {"fig1_wrong_version": fig1(rr, FIGS / "fig1_wrong_version.png"),
            "fig2_commencement_delay": fig2(st, FIGS / "fig2_commencement_delay.png"),
            "fig3_change_profile": fig3(st, FIGS / "fig3_change_profile.png"),
            "fig4_examples_timeline": fig4(ex, FIGS / "fig4_examples_timeline.png")}
    (RES / "figures_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if APPLICANT:
        APPLICANT.mkdir(parents=True, exist_ok=True)
        for f in FIGS.glob("*.png"):
            shutil.copy2(f, APPLICANT / f.name)
    print(json.dumps(data, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
