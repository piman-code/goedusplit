# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Goedu-Split: a local PySide6 desktop app (macOS/Windows) that analyses NEIS 정오표 + 문항정보표 (+ 수행평가) files for 성취평가 and designs 예상정답률. Student data stays on the teacher's PC. UI text, docs and replies are Korean; keep file paths, commands and identifiers untranslated.

## Rules that apply here
- `/Users/piman/Projects/AGENTS.md` and `~/.claude/CLAUDE.md` apply: no `rm`/`git clean`/force-push etc. (use `/usr/bin/trash <absolute path>` after stating target and reason), no overwriting existing files with `>`/`mv`/`cp`, push/CI/downloads/Release only after explicit approval, no secrets or student data (names, IDs) in output or notes.
- The canonical project root is `/Users/piman/Projects/goedusplit`; DevDocs lives at `/Users/piman/DevDocs/10-프로젝트/linked/003-goedusplit/` (read `00-시작.md`, newest card in `90-세션-요약/`). Record substantive work as a new card there; do not rewrite existing DevDocs operating docs.
- Do not drive the app with Computer Use / accessibility automation (see "Known problems").

## Commands
Always use the project venv (`.venv/bin/python`, Windows: `.\.venv\Scripts\python.exe`); system `python3` lacks `pypdf` and fails 2 tests.
```bash
.venv/bin/python -m pip install --only-binary=:all: -r requirements-build-lock.txt   # pinned build env (requirements.txt is the loose list)
.venv/bin/python run.py                                   # run the real app (uses the user's real settings/save folders)
.venv/bin/python -B run_tests.py                          # all tests, isolated (temp settings/appdata, network blocked)
.venv/bin/python -B run_tests.py --pattern test_rounds.py # one file
.venv/bin/python -B -m unittest tests.test_rounds.CompareTests   # one class / test (isolation is applied by each test module)
node --test tests/test_expected_rate_web.cjs              # calculator (web) contract tests
.venv/bin/python run.py --synthetic-qa <new dir>          # frozen-app QA used by CI: 29 checks (isolated INI/appdata, off-the-record WebEngine, no network), output dir must not exist
.venv/bin/python -B tests/manual_analysis_flows.py --run --output <new dir>   # native analysis/export QA on a synthetic kit
.venv/bin/python -B tests/manual_calculator_flows.py --run                    # QtWebEngine calculator QA
```
There is no linter configured. QA scripts refuse an existing output directory; pass a fresh path.

Tests that open dialogs hang silently (offscreen Qt blocks on a modal). When a window test hangs, patch `QMessageBox.information/warning/critical` and the exact `QFileDialog` method the widget calls (`getOpenFileName` vs `getOpenFileNames`), and run under `faulthandler.dump_traceback_later(...)` to see where it stops.

## Build and release flow
- Never build in this checkout: `build_scripts/build_mac.sh` refuses to run if `build/` or `dist/` exist (`dist/` holds the preserved 1.0.5 app for rollback). Real candidates are built by GitHub Actions. The working branch is `codex/startup-optimized-20261007` (continues the older `codex/desktop-candidates-1.0.6`); a push to it builds a candidate automatically, other refs need `gh workflow run windows-build.yml --ref <branch> -f candidate_version=1.0.6` (a plain push elsewhere only runs tests). Commits marked `[skip ci]` build nothing. It builds Mac arm64 + Windows x64, runs tests and the frozen `--synthetic-qa`, and uploads `desktop-candidates-1.0.6-<sha>` plus per-OS `candidate-macos-<sha>` / `candidate-windows-<sha>`; a failed frozen QA uploads `failed-synthetic-qa-<os>-<sha>` with `NATIVE_CRASH.log`.
- The app version stays `1.0.6` across candidates; a candidate is identified by its full source SHA (`BUILD_SOURCE.json`, `BUILD-*.json`). After downloading (`gh run download <run> -n <artifact> -D artifacts/Goedu-Split-1.0.6-<sha7>`), verify `SHA256SUMS`, the SHA in `BUILD-*.json`, and `QA-*.json` (29/29, 0 errors). Artifacts expire after ~14 days.
- `goedusplit.spec` filters unused Qt modules out of the bundle (`_UNUSED_QT`); QtWebEngine (~290 MB) is required for the calculator, so size cannot shrink much further. Never keep PySide modules the app imports (QtQuick for `QQuickWidget`, WebEngine, WebChannel, QtTest for QA) in that list.
- Two school Windows helpers exist and must not be mixed: the old one (`build_scripts/make_school_validation_bundle.py`, `validate_school_candidate.ps1`, `.github/workflows/school-candidate-validation.yml`, `docs/WINDOWS_SCHOOL_QA.md`) pins the 65cfc79 candidate and its 12 checks; the current one is `docs/handoff/20261009/RUN_WINDOWS_CHECK.ps1` + compressed manifest for 9431156 (29 checks, see `docs/MAC_HANDOFF_20261009.md`). Moving to a new candidate means updating pinned constants only; do not weaken the checks.
- `build_scripts/package_assets.release_resources` drops only Windows WebEngine `.debug` resources that have a release counterpart (−77 MB); Mac bundles are unchanged by it.
- `artifacts/`, `out_test/`, `dist/`, `build/` are git-ignored working areas (`out_test` is investigation evidence, ~9 GB; do not delete without the user's say-so).

## Architecture
`run.py` → `app/main_window.py::run`. Everything UI-free is kept out of the window where possible:

- **Loaders** (`app/data_loader.py`, `perform_loader.py`, `cuts_loader.py`, `grade_cut_calculator.py`, `exam_structure.py`): NEIS Excel → dataclasses (`ExamData`, `StudentResponse`, `PerformData`, ...). `load_exam(item_info, responses)` accepts one file, a list, or paths joined with `|` (`PATH_SEPARATOR`, one 정오표 per class); `load_perform_many` does the same for 수행평가. Mixed exams, the same class twice or different score areas raise a `ValueError` that is shown to the user. `exam_structure.parse_document_xml` is the only way DOCX/HWPX XML is parsed (rejects DTD/entities, size cap).
- **Analysis** (`analysis.py`, `calibration.py`, `expected_rates.py`, `ai_review_logic.py`): `build_score_matrix` → `analyze_overall/items/serdap`. A cell `.` means correct, a digit is the wrong choice picked; `_answer_text` normalises Excel numbers (`3.0` → `3`).
- **Rounds** (`app/rounds.py`): per-exam summaries (`round_history/` under the AI material root, keyed subject+grade+year+semester+round, hashed students only) written on every analysis; compare/trend are pure functions. Separate from the portfolio store `subject_snapshots/` so exams are not counted twice. Semester/round are parsed from file names (`parse_round`), with a manual "시험 구분" override.
- **`main_window.py`** is a ~12k-line monolith holding all tabs (`_init_tab_*`), the sidebar (`FileSelector`, optional `multiple=True`), `run_analysis`, exports and folder auto-fill (`_pick_folder_batch`, keyword scoring per category, per-class grouping by `(n-m)`, same-round preference). `charts.py` holds the matplotlib figures, `theme.py`/`palettes.py` the look.
- **Deferred startup**: the window imports charts through `lazy_charts` (matplotlib loads on the first figure; `chart_canvas._MarginKeepingCanvas`), and `CanvasHolder.set_placeholder` shows text instead of empty figures. On Windows WebEngine loads when the calculator tab opens (`_load_webengine`, `_create_spliter_view`); on macOS it still loads at startup with a 1×1 `QQuickWidget` GPU anchor, otherwise the first calculator open recreates the window. `register_fonts(matplotlib_fonts=False)` at startup avoids the matplotlib font scan.
- **Portfolio** (`app/portfolio.py`): the current analysis is shown as an unsaved preview; "현재 과목 저장" writes a new uniquely named file opened with mode `x` (never overwrites); unreadable files are counted and left untouched.
- **Calculator**: `app/spliter_ox_web/` is a bundled web app shown in `QWebEngineView` and bridged through `QWebChannel` (it receives analysis evidence and returns projects/NEIS tables). Contract tests for it are Node tests.
- **AI features** (`ai_client.py`): local Ollama/MLX/LM Studio or CLI; nothing is sent anywhere by default.
- **Privacy** (`export_privacy.py`): student identity is pseudonymised with a per-install key (`student_hash`); real-identity exports need an explicit confirmation. Keep new storage hashed-only.
- **Test isolation** (`tests/runtime_isolation.py::ensure_isolated`): every test module calls it first; it redirects settings/appdata/caches and blocks the network. `app/synthetic_qa.py` is imported only for `--synthetic-qa`.

## Real NEIS files (learned the hard way)
Exports carry a legend row under the 정오표 ("※ . : 맞음 …") that must not become a student; some classes store choices as numbers; 일람표 files may be per exam (1차/2차) while 정오표 are per class (`(1-1)`); a 수행평가 일람표 is not a 교과목별 일람표. Test data lives outside the repo (`/Users/piman/Desktop/goedusplit 테스트 자료`); never copy student values into the repo.

## Known problems
- macOS: Qt's Cocoa accessibility code crashes (SIGSEGV in `libqcocoa`, `getAttributeValue:forObject:`) when an accessibility client such as Codex Computer Use queries the app; it does not occur with that permission off. The QtWebEngine renderer `SIGTRAP` under the external sandbox guard (P4) was investigated and shelved; do not change guard/sandbox settings.
- Windows and school acceptance (T01–T09 in `docs/PC_VALIDATION_RECORD.md`) are user-run; CI QA is not a substitute.
