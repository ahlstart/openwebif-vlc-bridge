#!/usr/local/bin/python3
"""Static file server (http.server) with HTTP Range / 206 support, so VLC can seek.

Usage: movie_http.py <port> <directory>
"""
from __future__ import annotations

import functools
import http.server
import os
import re
import sys
from typing import TYPE_CHECKING, AnyStr, BinaryIO

if TYPE_CHECKING:
    import io

    from _typeshed import SupportsRead, SupportsWrite


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    _range: tuple[int, int] | None = None   # (start, end) of the current 206 response

    def end_headers(self) -> None:
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self) -> io.BytesIO | BinaryIO | None:
        self._range = None
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or os.path.isdir(path):
            return super().send_head()
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
        if not m or m.groups() == ("", ""):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        st = os.fstat(f.fileno())
        size = st.st_size
        s, e = m.groups()
        if s == "":                       # bytes=-N (the last N bytes)
            start, end = max(0, size - int(e)), size - 1
        else:
            start = int(s)
            end = min(int(e), size - 1) if e else size - 1
        if start >= size or start > end:
            f.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(int(st.st_mtime)))
        self.end_headers()
        f.seek(start)
        self._range = (start, end)
        return f

    def copyfile(self, source: SupportsRead[AnyStr], outputfile: SupportsWrite[AnyStr]) -> None:
        try:
            if self._range is None:
                return super().copyfile(source, outputfile)
            remaining = self._range[1] - self._range[0] + 1
            while remaining > 0:
                buf = source.read(min(1 << 20, remaining))
                if not buf:
                    break
                outputfile.write(buf)
                remaining -= len(buf)
        except (BrokenPipeError, ConnectionResetError):
            pass                          # VLC drops the connection when seeking - normal


if __name__ == "__main__":
    port, directory = int(sys.argv[1]), sys.argv[2]
    RangeHandler.extensions_map = {**RangeHandler.extensions_map, ".ts": "video/mp2t"}
    handler = functools.partial(RangeHandler, directory=directory)
    http.server.ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()
