"""Qt chart canvas, imported only when displaying a figure."""
import warnings
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas


class _MarginKeepingCanvas(FigureCanvas):
    """Fits a chart's margins to its labels when the widget is smaller than the chart's design.

    Charts set margins as fractions of their designed size (e.g. bottom=0.18 of 3.9 in). In a
    shorter pane the same fraction left too little room and axis titles were cut off. Below the
    designed size the margins are measured from the actual labels (tight_layout); at or above it
    the designed margins are used as before.
    """

    def __init__(self, fig):
        super().__init__(fig)
        pars = fig.subplotpars
        # Decided once: tight_layout leaves a placeholder layout engine behind, which would read as
        # "the chart manages its own layout" on every later resize and freeze the first margins.
        self._own_layout = fig.get_layout_engine() is not None
        self._design_size = tuple(fig.get_size_inches())
        self._design_pars = {"left": pars.left, "right": pars.right, "bottom": pars.bottom, "top": pars.top}

    def resizeEvent(self, event):
        super().resizeEvent(event)
        fig = self.figure
        if self._own_layout:
            return
        w0, h0 = self._design_size
        w, h = fig.get_size_inches()
        fig.set_layout_engine(None)
        fig.subplots_adjust(**self._design_pars)
        if w < w0 - 0.05 or h < h0 - 0.05:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)  # "Tight layout not applied" on very small panes
                    fig.tight_layout(pad=0.5)
            except Exception:
                fig.subplots_adjust(**self._design_pars)
            fig.set_layout_engine(None)


