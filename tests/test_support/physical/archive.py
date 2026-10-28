"""Contract: qa_workbench.archive atomic records, owner isolation and bounded history.

The real store owns all create/read/replace/retention operations. Windows path
measurements also cover extended drive and UNC syntax without requiring a share.
"""
import os
import shutil
import tempfile
from pathlib import Path

from qa_workbench.archive import ArchiveStore, _windows_extended_path
from test_support.contracts.archive import OWNER, archive_payloads, windows_path_cases


def persist_deep_archive():
    with tempfile.TemporaryDirectory(prefix="qa-deep-archive-") as directory:
        base = Path(directory).absolute()
        root = base
        while len(str(root)) < 280:
            root = root / "operator-evidence-directory-with-a-long-name"
        try:
            # Hosts may append/rebind their family path after store construction.
            store = ArchiveStore(base)
            store.root = root
            initial = store.recent(OWNER)
            exists = root.exists()
            payloads = archive_payloads()
            for payload in payloads:
                store.save(OWNER, payload["job"]["id"], payload, limit=2)
            restored = ArchiveStore(root)
            latest = payloads[-1]["job"]["id"]
            path = restored._path(OWNER, latest)
            names = [entry.name for entry in path.parent.iterdir()]
            return {"logical_record_length": len(str(root / path.name)),
                    "logical_root_preserved": store.root == root and restored.root == root,
                    "exists_after_discovery": exists, "initial_history": initial,
                    "loaded": restored.load(OWNER, latest), "history": restored.recent(OWNER),
                    "expired": restored.load(OWNER, payloads[0]["job"]["id"]),
                    "wrong_owner_load": restored.load("another-owner", latest),
                    "owned_elsewhere": restored.owned_elsewhere("another-owner", latest),
                    "same_owner_elsewhere": restored.owned_elsewhere(OWNER, latest),
                    "record_count": sum(name.endswith(".json") for name in names),
                    "temporary_count": sum(name.endswith(".tmp") for name in names)}
        finally:
            # Cleanup must itself support the deep Windows records. Delete only
            # the exact disposable directory created above, through its same path.
            cleanup = Path("\\\\?\\" + str(base)) if os.name == "nt" else base
            if not os.path.samefile(cleanup, base):
                raise OSError("unexpected_archive_fixture_cleanup_path")
            shutil.rmtree(cleanup)


def windows_archive_paths():
    return [_windows_extended_path(value) for value, _ in windows_path_cases()]
