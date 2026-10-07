"""Choose release WebEngine resources before COLLECT; never remove output files."""
from pathlib import PurePosixPath


def release_resources(entries, target):
    if target != "win32":
        return list(entries)
    names = {str(entry[0]).replace("\\", "/") for entry in entries}
    result = []
    for entry in entries:
        dest = str(entry[0]).replace("\\", "/")
        name = PurePosixPath(dest).name
        debug = ((name.startswith("qtwebengine_") and name.endswith(".debug.pak"))
                 or name == "v8_context_snapshot.debug.bin")
        if debug and dest.replace(".debug.", ".") in names and "/PySide6/" in "/" + dest:
            continue
        result.append(entry)
    return result
