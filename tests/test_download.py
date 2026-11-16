"""Tests for the download utility."""

import warnings
from unittest.mock import MagicMock, patch

import pytest

import psimodpy
from psimodpy._download import download

VALID_OBO = b"format-version: 1.2\n\n[Term]\nid: MOD:00046\nname: O-phospho-L-serine\n"


def _response(body: bytes) -> MagicMock:
    response = MagicMock()
    response.read.return_value = body
    response.__enter__ = lambda s: s
    response.__exit__ = MagicMock(return_value=False)
    return response


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
    mock_response.read.return_value = VALID_OBO
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("psimodpy._download.urllib.request.urlopen", return_value=mock_response):
        result = download(dest=cached, force=True)

    assert result == cached
    assert cached.read_bytes() == VALID_OBO


def test_creates_parent_dirs(tmp_path):
    dest = tmp_path / "a" / "b" / "PSI-MOD.obo"

    mock_response = MagicMock()
    mock_response.read.return_value = VALID_OBO
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


BAD_BODIES = {
    "html": b"<html><body><h1>404: Not Found</h1></body></html>",
    "empty": b"",
    "plain-text": b"this is not an OBO file\n",
    "header-only": b"format-version: 1.2\nontology: mod\n",
    "binary": b"\x1f\x8b\x08\x00\xff\xfe\x00\x80",
}


@pytest.mark.parametrize("body", BAD_BODIES.values(), ids=BAD_BODIES.keys())
def test_bad_download_leaves_existing_cache_untouched(tmp_path, body):
    cached = tmp_path / "PSI-MOD.obo"
    cached.write_bytes(VALID_OBO)

    with patch("psimodpy._download.urllib.request.urlopen", return_value=_response(body)):
        with pytest.raises(psimodpy.PsimodParseError):
            download(dest=cached, force=True)

    assert cached.read_bytes() == VALID_OBO
    assert [p.name for p in tmp_path.iterdir()] == ["PSI-MOD.obo"]


@pytest.mark.parametrize("body", BAD_BODIES.values(), ids=BAD_BODIES.keys())
def test_bad_download_caches_nothing_and_leaves_no_part_file(tmp_path, body):
    dest = tmp_path / "sub" / "PSI-MOD.obo"

    with patch("psimodpy._download.urllib.request.urlopen", return_value=_response(body)):
        with pytest.raises(psimodpy.PsimodParseError):
            download(dest=dest)

    assert not dest.exists()
    assert list(dest.parent.iterdir()) == []


def test_bad_download_error_names_the_destination_not_the_part_file(tmp_path):
    dest = tmp_path / "PSI-MOD.obo"

    with patch("psimodpy._download.urllib.request.urlopen", return_value=_response(BAD_BODIES["html"])):
        with pytest.raises(psimodpy.PsimodParseError) as info:
            download(dest=dest)

    assert str(dest) in str(info.value)
    assert ".part" not in str(info.value)


def test_bad_download_is_not_returned_by_the_next_call(tmp_path):
    dest = tmp_path / "PSI-MOD.obo"

    with patch("psimodpy._download.urllib.request.urlopen", return_value=_response(BAD_BODIES["html"])):
        with pytest.raises(psimodpy.PsimodParseError):
            download(dest=dest)
    with patch("psimodpy._download.urllib.request.urlopen", return_value=_response(VALID_OBO)) as mock_urlopen:
        assert download(dest=dest) == dest

    mock_urlopen.assert_called_once()
    assert dest.read_bytes() == VALID_OBO


def test_download_does_not_repeat_parse_warnings(tmp_path):
    body = VALID_OBO + b"unknown_tag: whatever\n"
    dest = tmp_path / "PSI-MOD.obo"

    with patch("psimodpy._download.urllib.request.urlopen", return_value=_response(body)):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            download(dest=dest)

    assert caught == []
