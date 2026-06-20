"""Build zip archives from generated file maps."""

from __future__ import annotations

import io
import zipfile
from typing import Mapping


def build_zip(files: Mapping[str, str], *, prefix: str = "") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in sorted(files.items()):
            arcname = f"{prefix}{path}" if prefix else path
            zf.writestr(arcname, content)
    return buffer.getvalue()
