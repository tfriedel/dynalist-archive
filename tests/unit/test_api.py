"""Tests for DynalistApi — HTTP client with caching."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dynalist_export.api import DynalistApi


@pytest.fixture
def api_with_mock_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[DynalistApi, MagicMock]:
    """Create a DynalistApi with a real token file and mocked requests.Session."""
    token_file = tmp_path / "token.txt"
    token_file.write_text("test-token\n")
    monkeypatch.setattr(
        "dynalist_export.api.API_TOKEN_FILES", [token_file]
    )
    monkeypatch.setattr("dynalist_export.api.API_CACHE_PREFIX", None)

    with patch("dynalist_export.api.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        api = DynalistApi()

    return api, mock_session


def _make_response(data: dict[str, Any]) -> MagicMock:
    """Create a mock HTTP response with given JSON data."""
    response = MagicMock()
    response.json.return_value = data
    response.text = json.dumps(data)
    return response


def test_init_reads_token_from_first_found_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DynalistApi reads the API token from the first existing file."""
    token_file = tmp_path / "token.txt"
    token_file.write_text("my-secret-token\n")
    monkeypatch.setattr(
        "dynalist_export.api.API_TOKEN_FILES",
        [tmp_path / "missing.txt", token_file],
    )

    with patch("dynalist_export.api.requests.Session"):
        api = DynalistApi()

    assert api.api_token == "my-secret-token"


def test_init_raises_when_no_token_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DynalistApi raises RuntimeError when no token file is found."""
    monkeypatch.setattr(
        "dynalist_export.api.API_TOKEN_FILES",
        [tmp_path / "a.txt", tmp_path / "b.txt"],
    )

    with pytest.raises(RuntimeError, match="Cannot find dynalist token"):
        DynalistApi()


def test_call_sends_token_in_request_body(
    api_with_mock_session: tuple[DynalistApi, MagicMock],
) -> None:
    """API call injects token into the request JSON body."""
    api, mock_session = api_with_mock_session
    mock_session.post.return_value = _make_response({"_code": "Ok", "data": 1})

    api.call("file/list", {"key": "val"})

    call_args = mock_session.post.call_args
    sent_body = json.loads(call_args[0][1])
    assert sent_body["token"] == "test-token"
    assert sent_body["key"] == "val"


def test_call_returns_parsed_json_response(
    api_with_mock_session: tuple[DynalistApi, MagicMock],
) -> None:
    """API call returns the parsed JSON response."""
    api, mock_session = api_with_mock_session
    mock_session.post.return_value = _make_response(
        {"_code": "Ok", "files": [1, 2, 3]}
    )

    result = api.call("file/list", {})

    assert result == {"_code": "Ok", "files": [1, 2, 3]}


def test_call_raises_on_api_error(
    api_with_mock_session: tuple[DynalistApi, MagicMock],
) -> None:
    """API call raises RuntimeError when _code is not Ok."""
    api, mock_session = api_with_mock_session
    mock_session.post.return_value = _make_response(
        {"_code": "InvalidToken", "_msg": "bad token"}
    )

    with pytest.raises(RuntimeError, match="API call failed"):
        api.call("file/list", {})


def test_call_raises_on_http_error(
    api_with_mock_session: tuple[DynalistApi, MagicMock],
) -> None:
    """API call raises when HTTP status indicates failure."""
    api, mock_session = api_with_mock_session
    mock_session.post.return_value.raise_for_status.side_effect = Exception("500")

    with pytest.raises(Exception, match="500"):
        api.call("file/list", {})


def test_call_writes_cache_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API call writes response to cache when cache prefix is set."""
    token_file = tmp_path / "token.txt"
    token_file.write_text("test-token\n")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_prefix = str(cache_dir / "cache-")
    monkeypatch.setattr("dynalist_export.api.API_TOKEN_FILES", [token_file])
    monkeypatch.setattr("dynalist_export.api.API_CACHE_PREFIX", cache_prefix)

    with patch("dynalist_export.api.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        api = DynalistApi(from_cache=True)

    mock_session.post.return_value = _make_response({"_code": "Ok", "result": 42})
    api.call("file/list", {})

    cache_file = Path(cache_prefix + "file--list")
    assert cache_file.exists()
    assert json.loads(cache_file.read_text()) == {"_code": "Ok", "result": 42}


def test_call_reads_from_cache_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API call returns cached response without making HTTP request."""
    token_file = tmp_path / "token.txt"
    token_file.write_text("test-token\n")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_prefix = str(cache_dir / "cache-")
    monkeypatch.setattr("dynalist_export.api.API_TOKEN_FILES", [token_file])
    monkeypatch.setattr("dynalist_export.api.API_CACHE_PREFIX", cache_prefix)

    # Pre-populate cache
    cache_file = Path(cache_prefix + "file--list")
    cache_file.write_text(json.dumps({"_code": "Ok", "cached": True}))

    with patch("dynalist_export.api.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        api = DynalistApi(from_cache=True)

    result = api.call("file/list", {})

    assert result == {"_code": "Ok", "cached": True}
    mock_session.post.assert_not_called()
