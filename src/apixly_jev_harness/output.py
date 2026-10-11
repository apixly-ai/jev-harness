"""Count-only Python streams for CLI tasks; no retained text or OS-fd isolation."""

import contextlib
import io
import threading


class _BinaryDiscard(io.RawIOBase):
    def __init__(self):
        super().__init__()
        self.count = 0
        self.lock = threading.Lock()

    def writable(self):
        return True

    def write(self, data):
        if self.closed:
            raise ValueError("write_to_closed_task_stream")
        size = memoryview(data).nbytes
        with self.lock:
            self.count += size
        return size


class _TextDiscard(io.TextIOBase):
    def __init__(self):
        super().__init__()
        self.count = 0
        self.lock = threading.Lock()
        self.buffer = _BinaryDiscard()

    @property
    def encoding(self):
        return "utf-8"

    @property
    def errors(self):
        return "strict"

    def writable(self):
        return True

    def write(self, data):
        if self.closed:
            raise ValueError("write_to_closed_task_stream")
        if not isinstance(data, str):
            raise TypeError("text_task_stream_requires_str")
        size = len(data)  # Unicode code points, not encoded bytes. No copy/retention.
        with self.lock:
            self.count += size
        return size


class TaskOutput:
    def __init__(self):
        self.stdout, self.stderr = _TextDiscard(), _TextDiscard()

    @contextlib.contextmanager
    def discard(self):
        # Process-global stream replacement; callers must not run overlapping CLI tasks.
        with contextlib.redirect_stdout(self.stdout), contextlib.redirect_stderr(self.stderr):
            yield

    def summary(self):
        channels = {
            name: {"characters": sink.count, "binary_bytes": sink.buffer.count}
            for name, sink in (("stdout", self.stdout), ("stderr", self.stderr))
        }
        if not any(value for channel in channels.values() for value in channel.values()):
            return None
        return {"policy": "discard", "scope": "python_streams", **channels}
