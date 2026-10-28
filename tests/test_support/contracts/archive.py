"""Independent synthetic archive payloads and Windows filesystem path contracts."""

OWNER = "deep-archive-owner"


def archive_payloads():
    return [
        {"owner": OWNER, "job": {"id": str(index) * 32,
                                 "finished_at": f"2026-01-0{index}T00:00:00+00:00"},
         "report": {"result": f"synthetic-evidence-{index}"}, "review": {}, "state": {}}
        for index in (1, 2, 3)
    ]


def windows_path_cases():
    return [
        (r"C:\operator\archives", r"\\?\C:\operator\archives"),
        (r"\\server\share\archives", r"\\?\UNC\server\share\archives"),
        (r"\\?\C:\operator\archives", r"\\?\C:\operator\archives"),
        (r"\\?\UNC\server\share\archives", r"\\?\UNC\server\share\archives"),
        (r"C:\operator\unused\..\archives", r"\\?\C:\operator\archives"),
    ]
