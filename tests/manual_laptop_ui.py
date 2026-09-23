"""Opt-in, synthetic-only QtWebEngine laptop regression checks.

Run from the repository with its existing Qt environment:
    .venv/bin/python tests/manual_laptop_ui.py --run

Screenshots and metrics.json go to a new temporary directory, or a new directory
specified by --output. This file is intentionally outside unittest discovery.
QT_QPA_PLATFORM defaults to offscreen; it never attaches to a running app.
"""

import argparse
import copy
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


def synthetic_project():
    judges = [{"id": f"synthetic-judge-{n}", "name": f"Synthetic Review {n}"} for n in (1, 2)]
    items = []
    for number in range(1, 19):
        items.append({
            "id": f"synthetic-item-{number}",
            "number": number,
            "title": f"Synthetic item {number}",
            "type": "\uc120\ud0dd\ud615",
            "difficulty": "\ubcf4\ud1b5",
            "targetLevel": "C",
            "points": 5,
            "sampleSize": 3,
            "standard": "Synthetic standard",
            "note": "Synthetic only",
            "evidence": [],
            "judgmentsByJudge": {
                judge["id"]: {
                    level: {
                        "correct": [index < count for index in range(3)],
                        "targetRate": rate,
                        "overrideRate": None,
                    }
                    for level, count, rate in zip("ABCDE", (3, 2, 2, 1, 0), (100, 80, 60, 40, 20))
                }
                for judge in judges
            },
        })
    return {
        "version": 1,
        "judges": judges,
        "activeJudgeId": judges[1]["id"],
        "items": items,
        "evidenceData": None,
        "evidenceMode": "difficultyAverage",
    }


DOM_METRICS = r"""
(() => {
  const box = element => {
    if (!element) return null;
    const r = element.getBoundingClientRect(), s = getComputedStyle(element);
    let rendered = r.width > 0 && r.height > 0;
    let left = 0, top = 0, right = innerWidth, bottom = innerHeight;
    for (let parent = element; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (style.display === 'none' || style.visibility === 'hidden' ||
          style.visibility === 'collapse' || Number(style.opacity) === 0) rendered = false;
      if (parent === element) continue;
      const p = parent.getBoundingClientRect();
      const sx = parent.offsetWidth ? p.width / parent.offsetWidth : 1;
      const sy = parent.offsetHeight ? p.height / parent.offsetHeight : 1;
      if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) {
        left = Math.max(left, p.left + parent.clientLeft * sx);
        right = Math.min(right, p.left + (parent.clientLeft + parent.clientWidth) * sx);
      }
      if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
        top = Math.max(top, p.top + parent.clientTop * sy);
        bottom = Math.min(bottom, p.top + (parent.clientTop + parent.clientHeight) * sy);
      }
    }
    return {
      x: r.x, y: r.y, width: r.width, height: r.height,
      right: r.right, bottom: r.bottom, display: s.display, rendered,
      fontSize: parseFloat(s.fontSize),
      fullyVisible: rendered && r.left >= left - 1 && r.right <= right + 1 &&
        r.top >= top - 1 && r.bottom <= bottom + 1,
      scrollTop: element.scrollTop, clientHeight: element.clientHeight,
      clientWidth: element.clientWidth, scrollWidth: element.scrollWidth
    };
  };
  const wrap = document.querySelector('.item-table-wrap');
  const headers = [...document.querySelectorAll('.item-table thead th')];
  const w = box(wrap);
  const activeView = document.querySelector('[data-goedu-view][aria-selected="true"]')?.dataset.goeduView;
  const wrapScale = wrap?.offsetHeight ? w.height / wrap.offsetHeight : 1;
  const headBottom = Math.max(0, ...headers.map(th => box(th)).filter(b => b.rendered).map(b => b.bottom));
  const completeRows = [...document.querySelectorAll('.item-table tbody tr')].filter(row => {
    const r = box(row);
    return activeView === 'table' && w?.rendered && r.fullyVisible &&
      r.y >= Math.max(w.y, headBottom) - 1 &&
      r.bottom <= Math.min(w.y + (wrap.clientTop + wrap.clientHeight) * wrapScale, innerHeight) + 1;
  }).length;
  const toolbar = box(document.querySelector('.table-toolbar'));
  const scoreButton = document.querySelector('[data-score-details]');
  const project = window.__GOEDUSPLIT_GET_PROJECT__?.();
  const active = document.activeElement;
  return {
    viewport: [innerWidth, innerHeight], zoom: window.__GOEDUSPLIT_ZOOM__, activeView,
    theme: document.querySelector('[data-theme]')?.getAttribute('data-theme'),
    bodyWidth: document.body.scrollWidth, completeRows,
    boxes: Object.fromEntries([
      '.table-toolbar', '.item-table-wrap', '.detail-panel', '.side-panel',
      '.goedu-score-source', '.goedu-score-note'
    ].map(selector => [selector, box(document.querySelector(selector))])),
    headers: headers.map(th => ({name: th.textContent.trim(), ...box(th)})),
    inputs: [...document.querySelectorAll('.item-table input:not([type="checkbox"]), .item-table select')]
      .map(box).filter(b => b.rendered),
    controls: [...document.querySelectorAll('.table-controls button, .table-controls select')].map(e => {
      const r = box(e);
      return {
        label: e.getAttribute('aria-label') || e.title || e.textContent.trim(),
        tag: e.tagName, ...r,
        withinToolbar: r.rendered && r.x >= toolbar.x - 1 && r.right <= toolbar.right + 1 &&
          r.y >= toolbar.y - 1 && r.bottom <= toolbar.bottom + 1,
        contentFits: e.scrollWidth <= e.clientWidth + 1 && e.scrollHeight <= e.clientHeight + 1
      };
    }),
    views: [...document.querySelectorAll('.table-toolbar [data-goedu-view]')].map(button => ({
      value: button.dataset.goeduView, selected: button.getAttribute('aria-selected'),
      ...box(button)
    })),
    scoreExpanded: scoreButton?.getAttribute('aria-expanded'),
    scoreSource: document.querySelector('.goedu-score-source')?.textContent.trim(),
    scoreNote: document.querySelector('.goedu-score-note')?.textContent.trim(),
    focus: {
      table: !!wrap && (active === wrap || wrap.contains(active)),
      right: !!active?.closest('.detail-panel'),
      left: !!active?.closest('.side-panel')
    },
    itemCount: project?.items.length, selectedId: project?.selectedId,
    activeJudgeId: project?.activeJudgeId
  };
})()
"""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class LaptopProbe:
    def __init__(self, app, window, out, prefix, qt_test, point, left_button):
        self.app, self.window, self.out, self.prefix = app, window, out, prefix
        self.qt_test, self.point, self.left_button = qt_test, point, left_button
        self.records = []

    def javascript(self, expression, timeout=10):
        result = []
        source = (
            "JSON.stringify((() => { try { return {ok: true, value: (" + expression +
            ")}; } catch (error) { return {ok: false, error: String(error)}; } })())"
        )
        self.window.spliter_view.page().runJavaScript(source, result.append)
        deadline = time.monotonic() + timeout
        while not result and time.monotonic() < deadline:
            self.qt_test.qWait(25)
        require(bool(result) and isinstance(result[0], str), "WebEngine JavaScript callback timed out")
        response = json.loads(result[0])
        require(response["ok"], response.get("error", "JavaScript evaluation failed"))
        return response.get("value")

    def wait_for(self, expression, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.javascript(expression):
                return
            self.qt_test.qWait(50)
        raise AssertionError(f"DOM condition timed out: {expression}")

    def click(self, selector):
        position = self.javascript(
            "(() => { const e = document.querySelector(" + json.dumps(selector) +
            "); if (!e || e.disabled) return null; const r = e.getBoundingClientRect();"
            "return r.width && r.height ? [r.x + r.width / 2, r.y + r.height / 2] : null; })()"
        )
        require(position is not None, f"Control is missing, hidden or disabled: {selector}")
        view = self.window.spliter_view
        target = view.focusProxy() or view
        target.setFocus()
        self.qt_test.mouseClick(
            target, self.left_button,
            pos=self.point(round(position[0]), round(position[1])),
        )
        self.qt_test.qWait(150)

    def native_tools(self):
        from PySide6.QtCore import QRect
        from PySide6.QtWidgets import QAbstractButton

        toolbar = self.window.spliter_toolbar
        result = []
        for button in toolbar.findChildren(QAbstractButton):
            origin = button.mapTo(self.window, self.point(0, 0))
            rect = QRect(origin, button.size())
            local = QRect(button.mapTo(toolbar, self.point(0, 0)), button.size())
            result.append({
                "label": button.text(), "rect": [rect.x(), rect.y(), rect.width(), rect.height()],
                "visible": button.isVisibleTo(self.window),
                "withinWindow": self.window.rect().contains(rect),
                "withinToolbar": toolbar.rect().contains(local),
            })
        return result

    def capture(self, label):
        self.qt_test.qWait(1250)
        self.javascript("""(() => {
          window.__laptopFrameReady = false;
          requestAnimationFrame(() => requestAnimationFrame(() => {window.__laptopFrameReady = true;}));
          return true;
        })()""")
        self.wait_for("window.__laptopFrameReady === true")
        geometry = """JSON.stringify([
          innerWidth, innerHeight,
          [...document.querySelectorAll('.table-toolbar, .table-controls button, .table-controls select, .item-table-wrap, .detail-panel, .side-panel')]
            .map(e => {const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height];})
        ])"""
        prior = self.javascript(geometry)
        deadline = time.monotonic() + 5
        while True:
            self.qt_test.qWait(100)
            current = self.javascript(geometry)
            if current == prior:
                break
            require(time.monotonic() < deadline, "Layout geometry did not settle before screenshot")
            prior = current
        result = self.javascript(DOM_METRICS)
        result.update(window=[self.window.width(), self.window.height()],
                      sidebar=self.window.splitter.sizes(), step=label, geometryStable=True,
                      settleMs=1250, nativeZoom=self.window._zoom_percent(),
                      nativeTools=self.native_tools())
        screenshot = self.out / f"{self.prefix}-{label}.png"
        pixmap = self.window.grab()
        require(not pixmap.isNull() and pixmap.save(str(screenshot)), "Screenshot capture failed")
        result["screenshot"] = screenshot.name
        self.records.append(result)
        return result

    def project(self):
        return self.javascript("window.__GOEDUSPLIT_GET_PROJECT__()")

    def switch_view(self, view):
        self.click(f'.table-toolbar [data-goedu-view="{view}"]')
        self.wait_for(
            'document.querySelector(\'[data-goedu-view="' + view +
            '"]\')?.getAttribute("aria-selected") === "true"'
        )

    def check(self, width, height, min_rows, theme):
        self.wait_for(
            "window.__GOEDUSPLIT_GET_PROJECT__?.().items[0]?.id === 'synthetic-item-1' && "
            "document.querySelectorAll('.table-toolbar [data-goedu-view]').length === 3"
        )
        # Let the native post-load zoom/theme timers and CSS loading settle.
        self.qt_test.qWait(1500)
        initial = self.capture("table-default")
        print(f"{self.prefix}: initial {initial['completeRows']} complete rows, "
              f"web={initial['viewport']}, screenshot={initial['screenshot']}", flush=True)
        require(initial["window"] == [width, height], "Native viewport was clamped")
        require(initial["sidebar"][0] <= 4, "Calculator sidebar did not collapse by default")
        require(initial["theme"] == theme, f"WebEngine theme did not become {theme}")
        require(initial["itemCount"] == 18, "Synthetic project was not loaded")
        require(initial["completeRows"] >= min_rows,
                f"{width}x{height}: {initial['completeRows']} complete rows, expected >= {min_rows}")
        require({v["value"] for v in initial["views"]} == {"table", "right", "left"},
                "Toolbar must expose table/right/left modes")
        require(all(v["fullyVisible"] for v in initial["views"]), "A view tab is clipped")
        require(next(v for v in initial["views"] if v["value"] == "table")["selected"] == "true",
                "Table must be the default mode")
        for label in [*"ABCDE", "\uc720\ud615", "\uac00\uc0c1\ud559\uc0dd"]:
            header = next((h for h in initial["headers"] if h["name"] == label), None)
            require(header and header["fullyVisible"], f"Required header is hidden or clipped: {label}")
        require(initial["bodyWidth"] <= initial["viewport"][0] + 1, "Page overflows horizontally")
        require(initial["zoom"] == 100 and initial["nativeZoom"] == 100, "Baseline must use 100% zoom")
        require(initial["inputs"] and all(i["fontSize"] >= 13 for i in initial["inputs"]),
                "Table inputs are smaller than 13px")
        require(all(h["fontSize"] >= 12 for h in initial["headers"] if h["rendered"]),
                "Table headers are smaller than 12px")

        before = self.project()
        for selector in (".goedu-score-source", ".goedu-score-note"):
            require(initial["boxes"][selector] and not initial["boxes"][selector]["rendered"],
                    f"Score comparison must be collapsed by default: {selector}")
        require(initial["scoreExpanded"] == "false", "Score toggle has wrong collapsed aria state")
        self.click("[data-score-details]")
        expanded = self.capture("score-expanded")
        require(expanded["scoreExpanded"] == "true", "Score comparison did not expand")
        for selector in (".goedu-score-source", ".goedu-score-note"):
            require(expanded["boxes"][selector]["fullyVisible"], f"Expanded comparison is clipped: {selector}")
        require("18" in expanded["scoreSource"], "Expanded source omits synthetic item count")
        require("\uc6d0\uc810\uc218" in expanded["scoreNote"] and "NEIS" in expanded["scoreNote"],
                "Expanded comparison omits original/NEIS scores")
        self.click("[data-score-details]")
        collapsed = self.javascript(DOM_METRICS)
        require(collapsed["scoreExpanded"] == "false", "Score comparison did not close")
        require(all(not collapsed["boxes"][s]["rendered"] for s in
                    (".goedu-score-source", ".goedu-score-note")), "Comparison remains visible after closing")
        require(self.project() == before, "Opening score comparison changed project state")

        self.javascript("""(() => {
          const row = document.querySelectorAll('.item-table tbody tr')[9];
          row.scrollIntoView({block: 'center', inline: 'nearest'});
          row.click();
          return true;
        })()""")
        self.wait_for("window.__GOEDUSPLIT_GET_PROJECT__().selectedId === 'synthetic-item-10'")
        self.javascript("""(() => {
          document.querySelectorAll('.item-table tbody tr')[9]
            .querySelector('.points-input').focus({preventScroll: true});
          return true;
        })()""")
        scroll_top = self.javascript("document.querySelector('.item-table-wrap').scrollTop")
        require(scroll_top > 0, "Scroll restoration check did not establish a scrolled table")
        before = self.project()
        self.switch_view("right")
        editor = self.capture("selected-editor")
        print(f"{self.prefix}: editor={editor['boxes']['.detail-panel']}", flush=True)
        require(editor["completeRows"] == 0, "Hidden table was counted as complete rows")
        require(not editor["boxes"][".item-table-wrap"]["rendered"], "Table remains visible during editing")
        detail = editor["boxes"][".detail-panel"]
        require(detail["fullyVisible"] and detail["height"] >= 300,
                f"Selected-item editor is clipped or shorter than 300px: {detail}")
        require(detail["width"] >= initial["boxes"][".item-table-wrap"]["width"] - 2,
                "Selected-item editor does not use the full workspace width")
        require(editor["focus"]["right"], "Focus did not enter the selected-item editor")
        require(self.project() == before, "Entering edit mode changed selection or project state")

        self.javascript("""(() => {
          const input = document.querySelectorAll('.level-editor')[2].querySelectorAll('input')[1];
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, '63.25');
          input.dispatchEvent(new Event('input', {bubbles: true}));
          input.dispatchEvent(new Event('change', {bubbles: true}));
          return true;
        })()""")
        self.wait_for("""(() => {
          const p = window.__GOEDUSPLIT_GET_PROJECT__();
          return p.items[9].judgmentsByJudge[p.activeJudgeId].C.overrideRate === 63.25;
        })()""")
        expected = copy.deepcopy(before)
        expected["items"][9]["judgmentsByJudge"][expected["activeJudgeId"]]["C"]["overrideRate"] = 63.25
        require(self.project() == expected, "Editing C changed unrelated values or selection")

        self.switch_view("left")
        left = self.capture("review-evidence")
        require(left["completeRows"] == 0, "Hidden table was counted in review/evidence mode")
        require(left["boxes"][".side-panel"]["fullyVisible"], "Review/evidence panel is clipped")
        require(not left["boxes"][".item-table-wrap"]["rendered"] and
                not left["boxes"][".detail-panel"]["rendered"], "Workspace modes overlap")
        require(left["focus"]["left"], "Focus did not enter the review/evidence panel")
        require(self.project() == expected, "Switching to review/evidence lost the edit")
        self.switch_view("table")
        returned = self.capture("table-returned")
        require(returned["boxes"][".item-table-wrap"]["fullyVisible"], "Table did not return")
        require(not returned["boxes"][".detail-panel"]["rendered"] and
                not returned["boxes"][".side-panel"]["rendered"], "Editor remains visible in table mode")
        require(abs(returned["boxes"][".item-table-wrap"]["scrollTop"] - scroll_top) <= 1,
                "Returning to the table lost its scroll position")
        require(returned["focus"]["table"], "Focus did not return to the table or a table field")
        require(self.project() == expected, "View roundtrip lost edit, selection, judge or project state")
        returned["projectDigest"] = hashlib.sha256(
            json.dumps(expected, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def check_toolbar_resizes(self, width, height):
        self.switch_view("table")
        before = self.project()
        checks = []
        for zoom in (100, 120, 160):
            self.window._set_zoom(zoom)
            self.window.resize(width, height)
            for sidebar_open in (False, True):
                check = {"zoom": zoom, "sidebarOpen": sidebar_open}
                try:
                    if (self.window.splitter.sizes()[0] > 4) != sidebar_open:
                        self.qt_test.mouseClick(self.window.btn_sidebar, self.left_button)
                    label = f"tools-{zoom}-sidebar-{'open' if sidebar_open else 'closed'}"
                    measured = self.capture(label)
                    check["viewport"] = measured["viewport"]
                    require(measured["window"] == [width, height], "Native window was clamped after zoom")
                    require((measured["sidebar"][0] > 4) == sidebar_open, "Sidebar toggle did not persist")
                    require(measured["zoom"] == zoom and measured["nativeZoom"] == zoom,
                            "Web/native zoom did not reach the requested value")
                    require(len(measured["controls"]) >= 3, "Toolbar controls are missing")
                    clipped = [control for control in measured["controls"]
                               if not control["fullyVisible"] or not control["withinToolbar"]]
                    require(not clipped, "Clipped web toolbar controls: " +
                            ", ".join(control["label"] for control in clipped))
                    for label in ("\uc790\ub8cc", "NEIS \uc785\ub825\ud45c"):
                        native = next((b for b in measured["nativeTools"] if b["label"] == label), None)
                        require(native and native["visible"] and native["withinWindow"] and native["withinToolbar"],
                                f"Native toolbar button is hidden or clipped: {label}")
                    require(self.project() == before, "Zoom or sidebar resize changed project state")
                    check["status"] = "passed"
                except Exception as error:
                    check["status"], check["error"] = "failed", str(error)
                checks.append(check)
        return checks


def run(out):
    with tempfile.TemporaryDirectory(prefix="goedusplit-laptop-profile-") as scratch:
        scratch = Path(scratch)
        environment = {
            "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "offscreen"),
            "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --disable-gpu-compositing --disable-gpu-rasterization --disable-zero-copy",
            "MPLCONFIGDIR": str(scratch / "matplotlib"),
            "XDG_CACHE_HOME": str(scratch / "cache"),
        }
        with patch.dict(os.environ, environment):
            from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSettings, Qt
            from PySide6.QtTest import QTest
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
            from PySide6.QtWidgets import QApplication

            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from app.main_window import MainWindow
            from app.theme import ThemeManager

            require(QApplication.instance() is None, "Run as a separate process, not inside another app")
            app = QApplication([])
            profile = QWebEngineProfile(app)
            require(profile.isOffTheRecord(), "WebEngine profile must not persist browser state")
            profile.setCachePath(str(scratch / "web-cache"))
            profile.setPersistentStoragePath(str(scratch / "web-storage"))
            profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
            profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)

            class LocalOnly(QWebEngineUrlRequestInterceptor):
                def interceptRequest(self, request):
                    if request.requestUrl().scheme() not in {"file", "qrc", "data", "blob", "about"}:
                        request.block(True)

            interceptor = LocalOnly(profile)
            profile.setUrlRequestInterceptor(interceptor)
            theme = ThemeManager(app)
            report = {"syntheticOnly": True, "platform": environment["QT_QPA_PLATFORM"],
                      "offTheRecord": True, "cases": []}
            for mode in ("light", "dark"):
                theme.set_mode(mode)
                for width, height, min_rows in ((1280, 800, 8), (1080, 720, 6)):
                    theme.set_base_font_pt(13)
                    prefix = f"{mode}-{width}x{height}"
                    settings = QSettings(str(scratch / f"{prefix}.ini"), QSettings.IniFormat)
                    settings.setFallbacksEnabled(False)
                    with patch("app.main_window.QSettings", return_value=settings), \
                         patch("app.main_window.QWebEnginePage", side_effect=lambda parent: QWebEnginePage(profile, parent)):
                        window = MainWindow(theme_manager=theme)
                        probe = LaptopProbe(app, window, out, prefix, QTest, QPoint, Qt.LeftButton)
                        case = {"name": prefix, "minimumRows": min_rows, "captures": probe.records}
                        try:
                            require(window.settings is settings, "QSettings isolation failed")
                            window._spliter_pending_project_payload = synthetic_project()
                            window.show()
                            window.resize(width, height)
                            window.tabs.setCurrentWidget(window.tab_spliter)
                            probe.check(width, height, min_rows, mode)
                            case["status"] = "passed"
                        except Exception as error:
                            case["status"], case["error"] = "failed", str(error)
                            print(f"{prefix}: first failure - {error}", flush=True)
                            try:
                                probe.capture("failure")
                            except Exception as capture_error:
                                case["captureError"] = str(capture_error)
                        finally:
                            try:
                                case["toolbarChecks"] = probe.check_toolbar_resizes(width, height)
                                if any(check["status"] != "passed" for check in case["toolbarChecks"]):
                                    case["status"] = "failed"
                            except Exception as error:
                                case["status"], case["toolbarError"] = "failed", str(error)
                            window.close()
                            # MainWindow schedules post-load callbacks through 1200ms.
                            QTest.qWait(1300)
                            window.deleteLater()
                            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                            app.processEvents()
                        report["cases"].append(case)
                        print(f"{prefix}: {case['status']}" + (f" - {case['error']}" if "error" in case else ""), flush=True)
                        for check in case.get("toolbarChecks", []):
                            if check["status"] == "failed":
                                print(f"  zoom={check['zoom']} sidebarOpen={check['sidebarOpen']}: {check['error']}", flush=True)
            profile.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
            report["passed"] = all(case["status"] == "passed" for case in report["cases"])
            (out / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Artifacts: {out}", flush=True)
            return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Run the isolated native WebEngine checks")
    parser.add_argument("--output", type=Path, help="New output directory; existing directories are rejected")
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required; no Qt instance has been started")
    if args.output:
        out = args.output.expanduser().resolve()
        out.mkdir(parents=True, exist_ok=False)
    else:
        out = Path(tempfile.mkdtemp(prefix="goedusplit-laptop-ui-")).resolve()
    print(f"Artifacts: {out}", flush=True)
    return run(out)


if __name__ == "__main__":
    raise SystemExit(main())
