"""Utility for downloading the PSI-MOD OBO file from the HUPO-PSI GitHub repository."""

from __future__ import annotations

import urllib.request
from pathlib import Path

_PSIMOD_URL = "https://raw.githubusercontent.com/HUPO-PSI/psi-mod-CV/master/PSI-MOD.obo"
_CACHE_DIR = Path.home() / ".cache" / "psimodpy"
_CACHE_FILE = _CACHE_DIR / "PSI-MOD.obo"


def download_obo(dest: Path | str | None = None, *, force: bool = False) -> Path:
    """Fetch the PSI-MOD OBO file and cache it locally.

    Args:
        dest: Destination path. Defaults to ~/.cache/psimodpy/PSI-MOD.obo.
        force: If True, re-download even if the file already exists.

    Returns:
        Path to the downloaded file.
    """
    target = Path(dest) if dest is not None else _CACHE_FILE
    if target.exists() and not force:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(_PSIMOD_URL) as response:  # noqa: S310
        data = response.read()
    target.write_bytes(data)
    return target
