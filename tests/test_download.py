"""Tests for the download utility."""

from unittest.mock import MagicMock, patch

import pytest

from psimodpy._download import download


def test_cached_file_skips_download(tmp_path):
    cached = tmp_path / "PSI-MOD.obo"
    cached.write_text("cached content")

    with patch("psimodpy._download.urllib.request.urlopen") as mock_urlopen:
        result = download(dest=cached, force=False)

    mock_urlopen.assert_not_called()
    assert result == cached


def test_force_redownloads(tmp_path):
    cached = tmp_path / "PSI-MOD.obo"
    cached.write_text("old content")

    mock_response = MagicMock()
    mock_response.read.return_value = b"new content"
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("psimodpy._download.urllib.request.urlopen", return_value=mock_response):
        result = download(dest=cached, force=True)

    assert result == cached
    assert cached.read_text() == "new content"


def test_creates_parent_dirs(tmp_path):
    dest = tmp_path / "a" / "b" / "PSI-MOD.obo"

    mock_response = MagicMock()
    mock_response.read.return_value = b"content"
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("psimodpy._download.urllib.request.urlopen", return_value=mock_response):
        result = download(dest=dest)

    assert result == dest
    assert dest.exists()


def test_default_dest_uses_cache():
    with (
        patch("psimodpy._download.urllib.request.urlopen") as mock_urlopen,
        patch("pathlib.Path.exists", return_value=True),
    ):
        result = download()

    mock_urlopen.assert_not_called()
    assert str(result).endswith("PSI-MOD.obo")


def test_failed_download_leaves_no_partial_file(tmp_path):
    dest = tmp_path / "PSI-MOD.obo"
    dest.write_text("old content")

    mock_response = MagicMock()
    mock_response.read.side_effect = OSError("connection reset")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with (
        patch("psimodpy._download.urllib.request.urlopen", return_value=mock_response),
        pytest.raises(OSError),
    ):
        download(dest=dest, force=True)

    assert dest.read_text() == "old content"
    assert [p.name for p in tmp_path.iterdir()] == ["PSI-MOD.obo"]
