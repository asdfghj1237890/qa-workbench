"""Private, bounded, atomic reviewed-evaluation archives under operator control."""
from __future__ import annotations

import hashlib
import json
import logging
import ntpath
import os
import re
import stat
import uuid
from datetime import datetime
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 1024
NAME = re.compile(r'^[0-9a-f]{64}\.[0-9a-f]{32}\.json$')
logger = logging.getLogger(__name__)


def _windows_extended_path(value):
    """Keep drive/UNC authority while bypassing Win32's legacy MAX_PATH limit."""
    value = ntpath.normpath(value)
    if value.startswith('\\\\?\\'):
        return value
    if value.startswith('\\\\'):
        return '\\\\?\\UNC\\' + value[2:]
    return '\\\\?\\' + value


def _filesystem_path(path):
    """Convert only I/O paths; callers retain the configured logical root."""
    absolute = Path(path).absolute()
    return Path(_windows_extended_path(str(absolute))) if os.name == 'nt' else absolute


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def _finished(payload):
    parsed = datetime.fromisoformat(payload['job']['finished_at'])
    if parsed.tzinfo is None:
        raise ValueError('invalid_archive_timestamp')
    return parsed


class ArchiveStore:
    max_bytes = MAX_BYTES

    def __init__(self, root):
        self.root = Path(root).absolute()

    @staticmethod
    def owner_hash(owner):
        return hashlib.sha256(owner.encode()).hexdigest()

    def _root(self, create=False):
        root = _filesystem_path(self.root)
        for part in (root, *root.parents):
            if part.is_symlink():
                raise OSError('unsafe_archive_root')
        if create:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.exists() and (not root.is_dir() or (os.name != 'nt' and root.stat().st_mode & 0o077)):
            raise OSError('unsafe_archive_root')

    def _path(self, owner, job_id):
        if not re.fullmatch(r'[0-9a-f]{32}', job_id):
            raise ValueError('invalid_archive_job_id')
        return _filesystem_path(self.root) / (self.owner_hash(owner) + '.' + job_id + '.json')

    def _read(self, path):
        path = _filesystem_path(path)
        if path.is_symlink():
            raise OSError('unsafe_archive_file')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        with os.fdopen(os.open(path, flags), 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_size > self.max_bytes
                    or (os.name != 'nt' and info.st_mode & 0o077)):
                raise OSError('unsafe_archive_file')
            raw = stream.read(self.max_bytes + 1)
        if len(raw) > self.max_bytes:
            raise OSError('oversized_archive')
        envelope = json.loads(raw)
        if (not isinstance(envelope, dict) or set(envelope) != {'version', 'sha256', 'payload'}
                or type(envelope['version']) is not int or envelope['version'] != 1
                or hashlib.sha256(_encoded(envelope['payload'])).hexdigest() != envelope['sha256']):
            raise ValueError('corrupt_archive')
        payload = envelope['payload']
        if (not isinstance(payload, dict) or set(payload) != {'owner', 'job', 'report', 'review', 'state'}
                or not isinstance(payload['owner'], str)
                or any(not isinstance(payload[key], dict) for key in ('job', 'report', 'review', 'state'))):
            raise ValueError('corrupt_archive_payload')
        return payload

    def _files(self):
        self._root()
        root = _filesystem_path(self.root)
        if not root.exists():
            return []
        result = []
        for path in root.iterdir():
            if NAME.fullmatch(path.name):
                result.append(path)
                if len(result) > MAX_FILES:
                    raise OSError('archive_capacity_exceeded')
        return result

    def load(self, owner, job_id):
        self._root()
        path = self._path(owner, job_id)
        if not path.exists() and not path.is_symlink():
            return None
        payload = self._read(path)
        if payload.get('owner') != owner or payload.get('job', {}).get('id') != job_id:
            raise ValueError('archive_owner_mismatch')
        return payload

    def recent(self, owner, limit=5):
        prefix = self.owner_hash(owner) + '.'
        files = [path for path in self._files() if path.name.startswith(prefix)]
        payloads = [self._read(path) for path in files]
        if any(payload.get('owner') != owner or payload['job'].get('id') != path.name.split('.')[1]
               for payload, path in zip(payloads, files, strict=True)):
            raise ValueError('archive_owner_mismatch')
        return sorted(payloads, key=_finished, reverse=True)[:limit]

    def owned_elsewhere(self, owner, job_id):
        target = self._path(owner, job_id)
        return any(path.name.endswith('.' + job_id + '.json') and path != target for path in self._files())

    def save(self, owner, job_id, payload, limit=5):
        self._root(create=True)
        target = self._path(owner, job_id)
        if target.is_symlink():
            raise OSError('unsafe_archive_file')
        # Everything that may reject the new review is checked before replace.
        # Existing corruption must never turn a committed review into HTTP 503.
        files = self._files()
        if target not in files and len(files) >= MAX_FILES:
            raise OSError('archive_capacity_exceeded')
        prefix = self.owner_hash(owner) + '.'
        generations = []
        for path in files:
            if path.name.startswith(prefix):
                previous = self._read(path)
                if (previous['owner'] != owner or previous['job'].get('id') != path.name.split('.')[1]
                        or not isinstance(previous['job'].get('finished_at'), str)):
                    raise ValueError('corrupt_archive_generation')
                if path != target:
                    generations.append((path, _finished(previous)))
        _finished(payload)
        generations.sort(key=lambda item: item[1], reverse=True)
        # A successful historical import must survive restart even when its
        # original execution predates every retained run. Keep this target and
        # the newest limit-1 other generations by actual, timezone-aware time.
        obsolete = [path for path, _ in generations[max(0, limit - 1):]]
        raw = _encoded({'version': 1, 'sha256': hashlib.sha256(_encoded(payload)).hexdigest(), 'payload': payload})
        if len(raw) > self.max_bytes:
            raise OSError('oversized_archive')
        temporary = _filesystem_path(self.root) / ('.' + uuid.uuid4().hex + '.tmp')
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
            with os.fdopen(os.open(temporary, flags, 0o600), 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if target.is_symlink():
                raise OSError('unsafe_archive_file')
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        # Replace is the commit boundary. Retention removes only preflighted,
        # strictly named files. Failed cleanup is retried on a later save; the
        # root's MAX_FILES ceiling still prevents unbounded accumulation.
        for path in obsolete:
            try:
                if path.is_symlink():
                    raise OSError('unsafe_archive_file')
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning('QA evaluation archive retention pending')
