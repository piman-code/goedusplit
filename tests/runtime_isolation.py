"""Process-local isolation for tests, including direct unittest discovery.

Import and call ensure_isolated before importing Qt, matplotlib, or app modules.
No HOME, CODEX_HOME, user settings, or installed application is changed.
"""
from __future__ import annotations

import atexit
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

_STATE_KEY = "_goedusplit_synthetic_runtime"


def secure_web_profile(profile):
    """Keep WebEngine ephemeral and reject every network URL in synthetic QA."""
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor

    class LocalOnly(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            if info.requestUrl().scheme().lower() not in {"file", "qrc", "data", "blob", "about"}:
                info.block(True)

    profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
    interceptor = LocalOnly(profile)
    profile.setUrlRequestInterceptor(interceptor)
    # Qt doesn't own this Python reference solely through setUrlRequestInterceptor.
    profile._goedusplit_local_only = interceptor
    return profile


def ensure_isolated(*, offscreen=True) -> Path:
    # Direct `python tests/manual_*.py` starts sys.path at tests/, not the repo.
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    existing = getattr(sys, _STATE_KEY, None)
    if existing is not None:
        return existing["root"]
    temporary = tempfile.TemporaryDirectory(prefix="goedusplit-synthetic-", ignore_cleanup_errors=True)
    root = Path(temporary.name)
    for name in ("appdata", "settings", "tmp", "matplotlib", "cache", "codex"):
        (root / name).mkdir()
    environment = {
        "MPLCONFIGDIR": str(root / "matplotlib"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "GOEDUSPLIT_CODEX_WORKDIR": str(root / "codex"),
        "GOEDUSPLIT_TEST_ROOT": str(root),
    }
    if offscreen:
        environment["QT_QPA_PLATFORM"] = "offscreen"
    environment_patch = patch.dict(os.environ, environment)
    environment_patch.start()
    # All later TemporaryDirectory calls, including writable-dir fallbacks, stay here.
    temporary_patch = patch.object(tempfile, "tempdir", str(root / "tmp"))
    temporary_patch.start()

    from PySide6.QtCore import QSettings
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWidgets import QApplication
    from app.main_window import MainWindow

    state = {"root": root, "temporary": temporary, "patches": [environment_patch, temporary_patch],
             "settings_count": 0, "profile": None}

    def isolated_settings(*_args, **_kwargs):
        state["settings_count"] += 1
        settings = QSettings(str(root / "settings" / f"window-{state['settings_count']}.ini"), QSettings.IniFormat)
        settings.setFallbacksEnabled(False)
        return settings

    def isolated_page(parent):
        if state["profile"] is None:
            state["profile"] = secure_web_profile(QWebEngineProfile(QApplication.instance()))
        return QWebEnginePage(state["profile"], parent)

    for protection in (
        patch("app.main_window.QSettings", side_effect=isolated_settings),
        patch.object(MainWindow, "_ai_material_root_dir", lambda _self: root / "appdata"),
        patch("app.main_window.QWebEnginePage", side_effect=isolated_page),
        patch("app.ai_client.CODEX_CLI_WORKDIR", root / "codex"),
        patch("app.ai_client._codex_cli_path_from_config", return_value=""),
        patch("urllib.request.urlopen", side_effect=AssertionError("Network access is forbidden in synthetic tests")),
    ):
        protection.start()
        state["patches"].append(protection)
    setattr(sys, _STATE_KEY, state)
    # Keep protection active for Qt destruction at process exit; only remove scratch files.
    atexit.register(temporary.cleanup)
    return root
