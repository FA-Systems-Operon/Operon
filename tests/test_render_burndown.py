"""The local burndown renderer must draw the same chart data as the workflow."""

import json
import runpy
import sys
import types
from unittest.mock import MagicMock

import pytest
from scripts import render_burndown

PNG = b"\x89PNG\r\n\x1a\n" + b"fake image"
SCRIPT = render_burndown.__file__


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "burndown_iteration9.csv"
    path.write_text(
        "date,remaining_points\n"
        "2026-11-04,23\n"
        "2026-11-05,23\n"
        "2026-11-07,15\n"
        "2026-11-09,0\n"
    )
    return path


@pytest.fixture
def quickchart(monkeypatch):
    """Replace QuickChart with a fake that records the chart it was sent."""
    sent = {}

    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return self.body

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["payload"] = json.loads(request.data)
        return Response(sent.get("reply", PNG))

    monkeypatch.setattr(render_burndown, "urlopen", fake_urlopen)
    return sent


def run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["render_burndown.py", *map(str, args)])
    render_burndown.main()


def test_trimmed_chart_ends_on_iteration_end_with_ideal_line(
    monkeypatch, quickchart, csv_path, tmp_path
):
    out = tmp_path / "chart.png"
    run(monkeypatch, csv_path, "--end", "2026-11-07", "--trim", "--out", out)

    chart = quickchart["payload"]["chart"]
    labels = chart["data"]["labels"]
    actual, ideal = chart["data"]["datasets"]
    assert quickchart["url"] == "https://quickchart.io/chart"
    assert labels == ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"]
    assert actual["data"] == [23, 23, None, 15]
    assert ideal["data"][0] == 23 and ideal["data"][-1] == 0
    assert chart["options"]["plugins"]["title"]["text"] == "iteration9 Burndown"
    assert out.read_bytes() == PNG


def test_without_end_date_draws_actual_line_only_next_to_csv(
    monkeypatch, quickchart, csv_path
):
    run(monkeypatch, csv_path)

    datasets = quickchart["payload"]["chart"]["data"]["datasets"]
    assert [d["label"] for d in datasets] == ["Actual Remaining"]
    assert csv_path.with_suffix(".png").read_bytes() == PNG


def test_end_date_after_last_row_extends_the_axis(monkeypatch, quickchart, csv_path):
    run(monkeypatch, csv_path, "--end", "2026-11-11")

    labels = quickchart["payload"]["chart"]["data"]["labels"]
    assert labels[-1] == "2026-11-11"


def test_trim_requires_end_date(monkeypatch, csv_path):
    with pytest.raises(SystemExit):
        run(monkeypatch, csv_path, "--trim")


def test_trim_before_first_row_leaves_nothing_to_plot(monkeypatch, csv_path):
    with pytest.raises(SystemExit, match="No rows to plot"):
        run(monkeypatch, csv_path, "--end", "2026-11-01", "--trim")


def test_rejects_a_reply_that_is_not_a_png(monkeypatch, quickchart, csv_path):
    quickchart["reply"] = b"<html>error</html>"
    with pytest.raises(SystemExit, match="did not return a PNG"):
        run(monkeypatch, csv_path)
    assert not csv_path.with_suffix(".png").exists()


def test_local_mode_draws_with_matplotlib_without_network(
    monkeypatch, csv_path, tmp_path
):
    pyplot = MagicMock()
    fig, ax = MagicMock(), MagicMock()
    pyplot.subplots.return_value = (fig, ax)
    matplotlib = types.ModuleType("matplotlib")
    matplotlib.use = MagicMock()
    matplotlib.pyplot = pyplot
    monkeypatch.setitem(sys.modules, "matplotlib", matplotlib)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", pyplot)
    monkeypatch.setattr(
        render_burndown, "urlopen", MagicMock(side_effect=AssertionError("network"))
    )

    out = tmp_path / "local.png"
    run(monkeypatch, csv_path, "--end", "2026-11-09", "--local", "--out", out)

    assert ax.plot.call_count == 2
    fig.savefig.assert_called_once()
    assert fig.savefig.call_args.args[0] == out


def test_runs_as_a_script(monkeypatch, csv_path):
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout: _png_response()
    )
    monkeypatch.setattr(sys, "argv", ["render_burndown.py", str(csv_path)])
    runpy.run_path(SCRIPT, run_name="__main__")
    assert csv_path.with_suffix(".png").read_bytes() == PNG


def _png_response():
    response = MagicMock()
    response.__enter__.return_value.read.return_value = PNG
    return response
