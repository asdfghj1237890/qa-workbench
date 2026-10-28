"""Bounded sanitized execution capture and detached restart snapshots.

Anonymous temporary files are never addressed by user paths. Only sanitized text
is written; pending partial lines stay private until redaction can see the line.
"""
from __future__ import annotations

import base64
import codecs
import json
import os
import re
import tempfile
from contextlib import ExitStack
from typing import BinaryIO, cast

from fastapi import HTTPException
from fastapi.responses import Response

from . import log_conclusion as _conclusion

MAX_CONCLUSION_BYTES = _conclusion.MAX_CONCLUSION_BYTES
render_conclusion = _conclusion.render_conclusion

MAX_BYTES = 8 * 1024 * 1024
PAGE_BYTES = 65536
_PRIVATE_KEY = re.compile(r"key|secret|password|token|credential|cookie|authorization", re.IGNORECASE)
_HEADER = re.compile(r"(?im)(\b(?:authorization|proxy-authorization|cookie|set-cookie)[\"']?\s*:\s*)[^\r\n]+")
_CREDENTIAL = re.compile(
    r"(?i)(\b(?:bearer|basic)\s+)[^\s,;\"']+|"
    r"((?<![\w-])(?:[\w-]{0,64}(?:api[_-]?key|secret|password|token|authorization|cookie)[\w-]{0,64})[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;\"']+)"
)
_PATH = re.compile(r"\b[A-Za-z]:[\\/][^\r\n\"']*|/(?:Users|home|private|tmp|var|qa-validation)/[^\s\"']+")
_URL_AUTH = re.compile(r"(https?://)[^\s/@]+:[^\s/@]+@", re.IGNORECASE)
_KEY_TOKEN = re.compile(r"\b(?:sk(?:-ant)?-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")


def secret_values(extra=()):
    # Include parent-only credentials too: exception text can originate outside
    # the minimal child environment. Never expose this set through job metadata.
    values = {value for key, value in os.environ.items()
              if _PRIVATE_KEY.search(key) and len(value) >= 4}
    values.update(value for value in extra if isinstance(value, str) and len(value) >= 4)
    # Multi-line credentials (for example PEM material) may be emitted one line
    # at a time; protecting only the full environment value would miss them.
    values.update(line for value in tuple(values) for line in value.splitlines() if len(line) >= 4)
    return tuple(sorted(values, key=len, reverse=True))


def sanitize(text, secrets=()):
    for value in secrets:
        text = text.replace(value, "[REDACTED]")
    text = _HEADER.sub(r"\1[REDACTED]", text)
    text = _CREDENTIAL.sub(lambda match: (match.group(1) or match.group(2)) + "[REDACTED]", text)
    text = _URL_AUTH.sub(r"\1[REDACTED]@", text)
    text = _KEY_TOKEN.sub("[REDACTED]", text)
    return _PATH.sub("[PRIVATE_PATH]", text).replace("\x00", "")


class RunLog:
    """Capture is complete once sealed; truncated independently means data loss."""
    def __init__(self, *, secrets=(), max_bytes=None, on_change=None):
        self.secrets = secret_values(secrets)
        self.max_bytes = MAX_BYTES if max_bytes is None else max_bytes
        self.files: dict[str | None, BinaryIO] = {}
        self._stack = ExitStack()
        self.pending: dict[str | None, str] = {}
        self.decoders: dict[str | None, codecs.IncrementalDecoder] = {}
        self.source_bytes = 0
        self.complete = False
        self.truncated = False
        self.failure: str | None = None
        self.closed = False
        self.conclusions: dict[str | None, bytes] = {}
        self.on_change = on_change

    def _file(self, step) -> BinaryIO:
        if step not in self.files:
            # Windows returns a delegating _TemporaryFileWrapper rather than
            # BinaryIO in typeshed; both expose the binary operations used here.
            self.files[step] = cast(BinaryIO, self._stack.enter_context(
                tempfile.TemporaryFile(mode="w+b", prefix="qa-sanitized-log-")  # noqa: SIM115 - service-owned ExitStack closes on eviction/shutdown.
            ))
        return self.files[step]

    def _write(self, step, text):
        if not text or self.failure or self.closed:
            return ""
        data = text.encode("utf-8")
        if self.source_bytes + len(data) > self.max_bytes:
            self.truncated, self.failure = True, "log_size_limit"
            return ""
        try:
            aggregate = self._file(None)
            aggregate.seek(0, 2)
            aggregate.write(data)
            aggregate.flush()
            if step is not None:
                output = self._file(step)
                output.seek(0, 2)
                output.write(data)
                output.flush()
            self.source_bytes += len(data)
        except (OSError, ValueError):
            self.truncated, self.failure = True, "log_storage_error"
            return ""
        if self.on_change is not None:
            self.on_change()
        return text

    def append(self, step, chunk):
        if self.complete or self.closed or self.failure:
            return ""
        decoder = self.decoders.setdefault(step, codecs.getincrementaldecoder("utf-8")("replace"))
        text = self.pending.get(step, "") + decoder.decode(chunk)
        # A single newline-free emission cannot grow unbounded in memory.
        if len(text.encode("utf-8")) > self.max_bytes:
            self.truncated, self.failure = True, "log_size_limit"
            self.pending.pop(step, None)
            return ""
        boundary = text.rfind("\n") + 1
        self.pending[step] = text[boundary:]
        return self._write(step, sanitize(text[:boundary], self.secrets))

    def finish_step(self, step):
        decoder = self.decoders.pop(step, None)
        text = self.pending.pop(step, "") + (decoder.decode(b"", final=True) if decoder else "")
        return self._write(step, sanitize(text, self.secrets))

    def event(self, step, event, **fields):
        # Callers pass only explicitly selected public fields, never a request,
        # HTTP headers, an exception repr, an ES document or a provider response.
        if self.complete:
            return ""
        text = json.dumps({"event": event, "step": step, **fields}, ensure_ascii=False) + "\n"
        # Structured telemetry is a different producer from the console. Its
        # newline must never flush a partial console token awaiting redaction.
        return self._write(step, sanitize(text, self.secrets))

    def finish(self):
        if self.complete:
            return
        for step in tuple(self.pending):
            self.finish_step(step)
        self.complete = True

    def mark_loss(self, reason):
        self.truncated = True
        self.failure = self.failure or reason

    def conclude(self, job):
        # Called after sealing/flushing and applying capture failures to the job.
        # A separate bounded suffix survives an exhausted capture budget and is
        # immutable, so UTF-8 cursors and the downloaded bytes stay identical.
        if not self.complete or self.conclusions:
            return
        scopes = [None, *[row["name"] for row in job.get("steps", [])[:32]]]
        for step in scopes:
            text = render_conclusion(job, step=step, truncated=self.truncated)
            self.conclusions[step] = sanitize(text, self.secrets).encode("utf-8")[:MAX_CONCLUSION_BYTES].decode("utf-8", "ignore").encode("utf-8")

    def read(self, offset=0, limit=PAGE_BYTES, step=None):
        try:
            stream = self.files.get(step)
            conclusion = self.conclusions.get(step, b"")
            if stream is None:
                captured = 0
            else:
                stream.seek(0, 2)
                captured = stream.tell()
            total = captured + len(conclusion)
            if offset > total:
                raise HTTPException(422, detail="invalid_log_offset")
            data = b""
            if stream is not None and offset < captured:
                stream.seek(offset)
                data = stream.read(min(limit, captured - offset))
            suffix_offset = max(0, offset - captured)
            if len(data) < limit:
                data += conclusion[suffix_offset:suffix_offset + limit - len(data)]
            # Reject a cursor inside a UTF-8 character; page end backs up.
            if data and data[0] & 0xC0 == 0x80:
                raise HTTPException(422, detail="invalid_log_offset")
            text = data.decode("utf-8", errors="ignore")
            end = offset + len(text.encode("utf-8"))
            return {"text": text, "next_offset": end, "total_bytes": total,
                    "has_more": end < total, "complete": self.complete,
                    "truncated": self.truncated, "legacy": False,
                    "conclusion_offset": captured if conclusion else None}
        except (OSError, ValueError):
            self.mark_loss("log_storage_error")
            raise HTTPException(503, detail="log_storage_unavailable") from None

    def download(self, step=None):
        # At most capture budget + bounded conclusion; the snapshot is stable on this
        # event loop even while subsequent worker chunks are still arriving.
        page = self.read(0, self.max_bytes + MAX_CONCLUSION_BYTES, step)
        return download_response(page["text"], page)

    def snapshot(self):
        """Only sanitized, committed bytes cross the persistence boundary.

        Do not save decoder/pending buffers: an incomplete console line can
        still contain a credential split across future chunks.
        """
        streams = []
        for step, stream in self.files.items():
            stream.seek(0)
            streams.append({"step": step, "data": base64.b64encode(stream.read()).decode("ascii")})
        return {"streams": streams, "conclusions": [
            {"step": step, "data": base64.b64encode(data).decode("ascii")}
            for step, data in self.conclusions.items()],
            "complete": self.complete, "truncated": self.truncated, "failure": self.failure}

    @classmethod
    def restore(cls, value):
        if (not isinstance(value, dict)
                or set(value) != {"streams", "conclusions", "complete", "truncated", "failure"}
                or type(value["complete"]) is not bool or type(value["truncated"]) is not bool
                or value["failure"] not in (None, "log_size_limit", "log_storage_error", "execution_interrupted")):
            raise ValueError("invalid_execution_log")
        log = cls()
        try:
            for key, maximum in (("streams", MAX_BYTES), ("conclusions", MAX_CONCLUSION_BYTES)):
                rows = value[key]
                if not isinstance(rows, list) or len(rows) > 33:
                    raise ValueError("invalid_execution_log_scopes")
                seen, total = set(), 0
                for row in rows:
                    if (not isinstance(row, dict) or set(row) != {"step", "data"}
                            or row["step"] is not None and (not isinstance(row["step"], str)
                                                          or len(row["step"]) > 200)
                            or row["step"] in seen or not isinstance(row["data"], str)
                            or len(row["data"]) > (maximum + 2) // 3 * 4):
                        raise ValueError("invalid_execution_log_scope")
                    seen.add(row["step"])
                    data = base64.b64decode(row["data"], validate=True)
                    data.decode("utf-8")
                    total += len(data)
                    if len(data) > maximum or total > (MAX_BYTES * 2 if key == "streams"
                                                       else MAX_CONCLUSION_BYTES * 33):
                        raise ValueError("oversized_execution_log")
                    if key == "streams":
                        log._file(row["step"]).write(data)
                    else:
                        log.conclusions[row["step"]] = data
            log.source_bytes = log.files[None].tell() if None in log.files else 0
            log.complete, log.truncated, log.failure = value["complete"], value["truncated"], value["failure"]
            return log
        except BaseException:
            log.close()
            raise

    def close(self):
        self.on_change = None
        self._stack.close()
        self.files.clear()
        self.pending.clear()
        self.decoders.clear()
        self.conclusions.clear()
        self.closed = True


def legacy_page(job, offset=0, limit=PAGE_BYTES, step=None):
    rows = [row for row in job.get("steps", []) if step is None or row["name"] == step]
    text = "\n".join(sanitize(row.get("log", ""), secret_values()) for row in rows)
    conclusion_offset = len(text.encode("utf-8"))
    conclusion = sanitize(render_conclusion(job, step=step, truncated=True, legacy=True), secret_values())
    text += conclusion
    data = text.encode("utf-8")
    if offset > len(data) or (offset < len(data) and data[offset] & 0xC0 == 0x80):
        raise HTTPException(422, detail="invalid_log_offset")
    chunk = data[offset:offset + limit].decode("utf-8", errors="ignore")
    end = offset + len(chunk.encode("utf-8"))
    return {"text": chunk, "next_offset": end, "total_bytes": len(data),
            "has_more": end < len(data), "complete": job.get("finished_at") is not None,
            "truncated": True, "legacy": True,
            "conclusion_offset": conclusion_offset if conclusion else None}


def download_response(text, page):
    return Response(text, media_type="text/plain; charset=utf-8", headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "attachment; filename=qa-execution.log.txt",
        "X-Log-Complete": str(page["complete"]).lower(),
        "X-Log-Truncated": str(page["truncated"]).lower(),
        "X-Log-Legacy": str(page["legacy"]).lower(),
    })
