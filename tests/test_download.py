"""Tests for the download_obo utility."""

from unittest.mock import MagicMock, patch

from psimodpy._download import download_obo


def test_cached_file_skips_download(tmp_path):
    cached = tmp_path / "PSI-MOD.obo"
    cached.write_text("cached content")

    with patch("psimodpy._download.urllib.request.urlopen") as mock_urlopen:
        result = download_obo(dest=cached, force=False)

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
        result = download_obo(dest=cached, force=True)

    assert result == cached
    assert cached.read_text() == "new content"


def test_creates_parent_dirs(tmp_path):
    dest = tmp_path / "a" / "b" / "PSI-MOD.obo"

    mock_response = MagicMock()
    mock_response.read.return_value = b"content"
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("psimodpy._download.urllib.request.urlopen", return_value=mock_response):
        result = download_obo(dest=dest)

    assert result == dest
    assert dest.exists()


def test_default_dest_uses_cache():
    with patch("psimodpy._download.urllib.request.urlopen") as mock_urlopen, patch(
        "pathlib.Path.exists", return_value=True
    ):
        result = download_obo()

    mock_urlopen.assert_not_called()
    assert str(result).endswith("PSI-MOD.obo")
