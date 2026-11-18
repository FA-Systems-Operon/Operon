"""Regenerate a burndown PNG from its CSV, without running the GitHub workflow.

Draws the same chart as .github/workflows/burndown.yml (QuickChart, Chart.js v4),
using only the dates and point totals in the CSV.

Examples:
    python scripts/render_burndown.py data/burndown_iteration3.csv --end 2026-11-03
    python scripts/render_burndown.py data/burndown_iteration3.csv --end 2026-11-03 --trim
    python scripts/render_burndown.py data/burndown_iteration3.csv --end 2026-11-03 --trim --local

--local draws the chart with matplotlib (pip install matplotlib) instead of QuickChart,
for when quickchart.io is unreachable. It looks close to, not identical to, the workflow's chart.
"""

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("csv_path", type=Path, help="e.g. data/burndown_iteration3.csv")
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        help="iteration end date (YYYY-MM-DD) for the ideal line",
    )
    parser.add_argument(
        "--trim",
        action="store_true",
        help="leave out rows after --end (chart only; the CSV is not changed)",
    )
    parser.add_argument(
        "--out", type=Path, help="output PNG (default: same name as the CSV, .png)"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="draw with matplotlib instead of QuickChart (no network)",
    )
    args = parser.parse_args()

    with args.csv_path.open(newline="") as handle:
        history = {
            date.fromisoformat(r["date"]): float(r["remaining_points"])
            for r in csv.DictReader(handle)
        }
    if args.trim:
        if not args.end:
            parser.error("--trim needs --end")
        history = {d: v for d, v in history.items() if d <= args.end}
    if not history:
        raise SystemExit("No rows to plot.")

    start = min(history)
    last = max(max(history), args.end or start)
    days = [start + timedelta(days=i) for i in range((last - start).days + 1)]
    datasets = [
        {
            "label": "Actual Remaining",
            "data": [history.get(day) for day in days],
            "borderColor": "#2563eb",
            "spanGaps": True,
            "fill": False,
        }
    ]
    if args.end and args.end > start:
        duration = (args.end - start).days
        datasets.append(
            {
                "label": "Ideal Burndown",
                "data": [
                    max(0.0, history[start] * (1 - (day - start).days / duration))
                    for day in days
                ],
                "borderColor": "#94a3b8",
                "borderDash": [6, 4],
                "pointRadius": 0,
                "fill": False,
            }
        )

    sprint = args.csv_path.stem.removeprefix("burndown_")
    out = args.out or args.csv_path.with_suffix(".png")
    if args.local:
        render_local(days, datasets, sprint, out)
        print(f"Wrote {out} ({len(days)} days, {start} to {last}).")
        return

    chart = {
        "type": "line",
        "data": {"labels": [d.isoformat() for d in days], "datasets": datasets},
        "options": {
            "plugins": {"title": {"display": True, "text": f"{sprint} Burndown"}},
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "Remaining story points"},
                }
            },
        },
    }
    request = Request(
        "https://quickchart.io/chart",
        data=json.dumps(
            {
                "chart": chart,
                "version": "4",
                "format": "png",
                "width": 1000,
                "height": 500,
                "backgroundColor": "white",
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=60) as response:
        png = response.read()
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SystemExit("QuickChart did not return a PNG image.")
    out.write_bytes(png)
    print(f"Wrote {out} ({len(days)} days, {start} to {last}).")


def render_local(days, datasets, sprint, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [d.isoformat() for d in days]
    fig, ax = plt.subplots(figsize=(10, 5), dpi=200)
    for ds in datasets:
        points = [(i, v) for i, v in enumerate(ds["data"]) if v is not None]
        xs, ys = zip(*points)
        ideal = "borderDash" in ds
        ax.plot(
            xs,
            ys,
            color=ds["borderColor"],
            linewidth=2.5 if not ideal else 2,
            linestyle=(0, (6, 4)) if ideal else "-",
            marker=None if ideal else "o",
            markerfacecolor="white",
            markersize=5,
            label=ds["label"],
        )
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(
        labels,
        rotation=30 if len(labels) > 12 else 0,
        ha="right" if len(labels) > 12 else "center",
        fontsize=8,
    )
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Remaining story points", color="#666")
    ax.set_title(f"{sprint} Burndown", color="#666", fontweight="bold", pad=34)
    ax.grid(color="#e5e5e5")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(
        loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=len(datasets), frameon=False
    )
    fig.tight_layout()
    fig.savefig(out, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
