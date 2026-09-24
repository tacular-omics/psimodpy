"""Utility for downloading the PSI-MOD OBO file from the HUPO-PSI GitHub repository."""

from __future__ import annotations

import os
import tempfile
import warnings
from pathlib import Path
from types import ModuleType

_PSIMOD_URL = "https://raw.githubusercontent.com/HUPO-PSI/psi-mod-CV/master/PSI-MOD.obo"
_CACHE_DIR = Path.home() / ".cache" / "psimodpy"
_CACHE_FILE = _CACHE_DIR / "PSI-MOD.obo"


def download(dest: Path | str | None = None, *, force: bool = False) -> Path:
    """Fetch the PSI-MOD OBO file and cache it locally.

    Args:
        dest: Destination path. Defaults to ~/.cache/psimodpy/PSI-MOD.obo.
        force: If True, re-download even if the file already exists; without it an
            existing file is returned as is.

    Returns:
        Path to the downloaded file.
    """
    target = Path(dest) if dest is not None else _CACHE_FILE
    if target.exists() and not force:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    import urllib.request

    # Download next to target, then rename: a failed download never leaves a truncated cache file.
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh, urllib.request.urlopen(_PSIMOD_URL) as response:  # noqa: S310
            fh.write(response.read())
        os.replace(tmp_name, target)
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    return target


def download_obo(dest: Path | str | None = None, *, force: bool = False) -> Path:
    """Deprecated alias of :func:`download`; will be removed in 2.0."""
    warnings.warn("download_obo() is deprecated; use download()", DeprecationWarning, stacklevel=2)
    return download(dest, force=force)


def __getattr__(name: str) -> ModuleType:
    """Import ``urllib`` on first attribute access, so ``_download.urllib.request`` still resolves.

    ``urllib.request`` (with ``http.client``, ``ssl`` and ``email``) is imported only when a
    download runs: it costs about 30 ms at import and most users never download.
    """
    if name == "urllib":
        import urllib.request

        return urllib
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
