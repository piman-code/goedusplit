"""Opt-in evidence retention for synthetic tests in a fresh output root."""
from pathlib import Path
import os
import shutil
import tempfile
import uuid


def enable(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    scratch = root / "scratch"
    archive = root / "retained"
    scratch.mkdir()
    archive.mkdir()
    tempfile.tempdir = str(scratch)
    original = tempfile.TemporaryDirectory

    class RetainedDirectory(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._finalizer.detach()

        def cleanup(self):
            self._finalizer.detach()
            if Path(self.name).exists():
                retain(self.name, ignore_errors=self._ignore_cleanup_errors)

    tempfile.TemporaryDirectory = RetainedDirectory

    def retain(path, *args, **kwargs):
        if args or kwargs.get("dir_fd") is not None:
            raise RuntimeError("Relative file descriptors cannot be retained safely")
        target = Path(path).resolve()
        if not target.is_relative_to(scratch) or target == scratch:
            raise RuntimeError("Refusing cleanup outside synthetic scratch: " + str(target))
        if not target.exists():
            if kwargs.get("ignore_errors"):
                return
            raise FileNotFoundError(target)
        destination = archive / (uuid.uuid4().hex + "-" + target.name)
        assert destination.is_relative_to(root) and not destination.exists()
        # Both absolute paths have been checked; rename preserves every byte.
        target.rename(destination)

    os.unlink = os.remove = retain
    shutil.rmtree = retain
    return root
