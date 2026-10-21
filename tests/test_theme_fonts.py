"""The bundled fonts must exist before the stylesheet names them (macOS hang on hosted CI)."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import unittest
from unittest.mock import patch


class FakeApp:
    def __init__(self, calls):
        self.calls = calls

    def setPalette(self, palette):
        pass

    def setStyleSheet(self, qss):
        self.calls.append("stylesheet")

    def font(self):
        from PySide6.QtGui import QFont
        return QFont()

    def setFont(self, font):
        pass


class ThemeFontOrderTests(unittest.TestCase):
    def test_bundled_fonts_are_registered_before_the_stylesheet_names_them(self):
        # Otherwise Core Text resolves "NanumGothic" as a downloadable system font and, with no
        # network, the first text layout waits forever (DownloadFontsForProperties).
        from app.theme import ThemeManager
        calls = []
        with patch("app.fonts.register_fonts", side_effect=lambda **kw: calls.append("fonts")) as register:
            ThemeManager(FakeApp(calls)).set_mode("light")
        self.assertEqual(["fonts", "stylesheet"], calls[:2])
        self.assertEqual({"matplotlib_fonts": False}, register.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
