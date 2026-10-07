import unittest
from build_scripts.package_assets import release_resources


class PackageAssetTests(unittest.TestCase):
    def test_windows_removes_only_redundant_debug_webengine_variants(self):
        names = ["PySide6/resources/qtwebengine_resources.pak",
                 "PySide6/resources/qtwebengine_resources.debug.pak",
                 "PySide6/resources/v8_context_snapshot.bin",
                 "PySide6/resources/v8_context_snapshot.debug.bin",
                 "PySide6/opengl32sw.dll", "PySide6/resources/icudtl.dat",
                 "PySide6/resources/LICENSE", "PySide6/resources/other.debug.pak"]
        entries = [(name, name, "DATA") for name in names]
        filtered = [entry[0] for entry in release_resources(entries, "win32")]
        self.assertEqual(filtered, [name for name in names if name not in (names[1], names[3])])
        self.assertEqual(release_resources(entries, "darwin"), entries)

    def test_no_release_counterpart_means_debug_variant_is_preserved(self):
        entries = [("PySide6/resources/qtwebengine_resources.debug.pak", "source", "DATA")]
        self.assertEqual(release_resources(entries, "win32"), entries)
