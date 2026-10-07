"""Load chart dependencies when a figure is requested, keeping the current theme."""
from importlib import import_module

_module = None
_colors = None


def set_theme(colors):
    global _colors
    _colors = dict(colors)
    if _module is not None:
        _module.set_theme(_colors)


def __getattr__(name):
    global _module
    if name.startswith("__"):
        raise AttributeError(name)
    if _module is None:
        module = import_module(".charts", __package__)
        from . import theme
        if theme._matplotlib_theme is not None:
            theme.ThemeManager._apply_matplotlib(*theme._matplotlib_theme)
        if _colors is not None:
            module.set_theme(_colors)
        _module = module
    return getattr(_module, name)
