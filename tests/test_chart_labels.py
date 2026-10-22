"""Chart labels stay readable: no value labels drawn over each other, nothing hidden under the
summary box, and colours that stand out from the chart background in both themes."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import unittest
from types import SimpleNamespace as NS

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_hex

from app import charts, palettes


def _items(n, seed=7):
    rng = np.random.default_rng(seed)
    return [NS(item=NS(number=i + 1, answer=3), p_value=float(rng.uniform(0.15, 1.0)),
               discrimination=float(rng.uniform(-0.15, 0.62))) for i in range(n)]


def _draw(fig, size=None):
    if size:
        fig.set_size_inches(*size)
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    return canvas.get_renderer()


def _overlaps(boxes):
    pairs = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if min(a.x1, b.x1) - max(a.x0, b.x0) > 0.5 and min(a.y1, b.y1) - max(a.y0, b.y0) > 0.5:
                pairs.append((a, b))
    return pairs


def _contrast(c1, c2):
    l1, l2 = charts._luminance(to_hex(c1)), charts._luminance(to_hex(c2))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


class ThemeCase(unittest.TestCase):
    def tearDown(self):
        charts.set_theme(palettes.LIGHT)

    def themes(self):
        for name, pal in (("light", palettes.LIGHT), ("dark", palettes.DARK)):
            charts.set_theme(pal)
            yield name, pal


class ItemValueLabelTests(ThemeCase):
    """Proposal 3: 25+ items in a pane narrower than the chart's design width."""

    def check(self, make):
        for n in (25, 30, 40):
            for size in ((8.2, 3.9), (6.4, 3.4)):
                fig = make(_items(n))
                renderer = _draw(fig, size)
                ax = fig.axes[0]
                shown = [t for t in ax.texts if t.get_visible() and t.get_text()]
                boxes = [t.get_window_extent(renderer) for t in shown]
                ticks = [t.get_window_extent(renderer) for t in ax.get_xticklabels() if t.get_visible() and t.get_text()]
                with self.subTest(items=n, size=size):
                    self.assertEqual(_overlaps(boxes + ticks), [])
                    self.assertGreaterEqual(len(shown), n // 2, "at least every other value stays on the chart")
                    frame = fig.bbox
                    for box in boxes:
                        self.assertTrue(box.x0 >= -1 and box.x1 <= frame.x1 + 1
                                        and box.y0 >= -1 and box.y1 <= frame.y1 + 1)

    def test_difficulty_labels_do_not_overlap(self):
        self.check(charts.fig_item_difficulty)

    def test_discrimination_labels_do_not_overlap(self):
        self.check(charts.fig_item_discrimination)

    def test_few_items_keep_every_label_at_full_size(self):
        fig = charts.fig_item_difficulty(_items(10))
        _draw(fig)
        texts = fig.axes[0].texts
        self.assertEqual(len([t for t in texts if t.get_visible()]), 10)
        self.assertTrue(all(t.get_rotation() == 0 and t.get_fontsize() == 8.5 for t in texts))


class NormalMonitoringTests(ThemeCase):
    """Proposal 8: the summary box covered the SD/level labels; the curve could pass the y limit."""

    def test_summary_box_stays_off_the_plot_and_curve_fits(self):
        rng = np.random.default_rng(3)
        cuts = {"A": 90, "B": 80, "C": 70, "D": 60, "E": 40}
        for totals in (np.clip(rng.normal(68, 13, 180), 0, 100),
                       np.clip(rng.normal(85, 4, 60), 0, 100),     # narrow, tall curve
                       np.array([20, 50, 50, 50, 95.0])):           # curve above the bars
            fig = charts.fig_score_normal_monitoring(totals, cuts, {"A": 9.0})
            renderer = _draw(fig)
            ax = fig.axes[0]
            note = next(t for t in ax.texts if "표준편차" in t.get_text())
            plot = ax.get_window_extent(renderer)
            box = note.get_bbox_patch().get_window_extent(renderer)
            self.assertTrue(box.x0 >= plot.x1 or box.y0 >= plot.y1 or box.y1 <= plot.y0,
                            "summary box must sit outside the plotting area")
            frame = fig.bbox
            self.assertTrue(box.x1 <= frame.x1 + 1 and box.y1 <= frame.y1 + 1)
            curve = next(line for line in ax.get_lines() if line.get_label() == "정규분포 곡선")
            self.assertLessEqual(max(curve.get_ydata()), ax.get_ylim()[1])
            labels = [t.get_window_extent(renderer) for t in ax.texts if t is not note]
            legend = ax.get_legend()
            if legend is not None:
                labels.append(legend.get_window_extent(renderer))
            self.assertEqual(_overlaps(labels), [])


class ChoiceDistributionColourTests(ThemeCase):
    """Proposal 14: fixed '#bbb'/white colours were faint on the dark theme."""

    def test_colours_follow_the_theme(self):
        dist = {lv: {1: .1, 2: .1, 3: .5, 4: .1, 5: .1, 0: .1} for lv in "ABCDE"}
        stats = NS(item=NS(answer=3), choice_dist_by_level=dist)
        for name, pal in self.themes():
            fig = charts.fig_choice_dist_by_level(stats)
            _draw(fig)
            ax = fig.axes[0]
            bg = pal["chart_bg"]
            for patch in ax.patches:
                with self.subTest(theme=name, label=patch.get_label()):
                    self.assertEqual(to_hex(patch.get_edgecolor()), to_hex(bg), "segment borders use the background")
            blank = next(c for c in ax.containers if c.get_label().startswith("무응답"))
            self.assertGreaterEqual(_contrast(blank.patches[0].get_facecolor(), bg), 3.0, name)
            for text in ax.texts:
                x, y = text.get_position()
                bar = next(p for p in ax.patches if p.contains_point(ax.transData.transform((x, y))))
                self.assertGreaterEqual(_contrast(text.get_color(), bar.get_facecolor()), 4.5, (name, text.get_text()))


class HighlightLineTests(ThemeCase):
    """Proposal 15: the pale-yellow light-theme highlight vanished on white."""

    def test_trend_lines_and_compare_bars_stand_out(self):
        trend = {"labels": ["1", "2", "3"], "mean": [60, 62, 64], "std": [10, 11, 12],
                 "a_pct": [10, 11, 12], "ab_pct": [30, 31, 32], "cut_a": [90, 88, 89]}
        base = {"label": "1차", "level_pct": {"A": 10, "B": 20}}
        other = {"label": "2차", "level_pct": {"A": 12, "B": 22}}
        for name, pal in self.themes():
            bg = pal["chart_bg"]
            fig = charts.fig_round_trend(trend)
            for ax in fig.axes:
                for line in ax.get_lines():
                    if len(line.get_xdata()) == 3 and line.get_linestyle() != "None":
                        self.assertGreaterEqual(_contrast(line.get_color(), bg), 3.0, (name, ax.get_title()))
            fig = charts.fig_round_compare(base, other)
            for patch in fig.axes[0].patches:
                self.assertGreaterEqual(_contrast(patch.get_facecolor(), bg), 3.0, name)


if __name__ == "__main__":
    unittest.main()
