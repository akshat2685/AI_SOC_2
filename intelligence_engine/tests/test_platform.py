import pytest
import sys
from unittest.mock import patch, MagicMock, call
import subprocess
from core.platform import platform_utils, PlatformAbstractor

def test_normalize_path():
    path = "some/test/path"
    normalized = platform_utils.normalize_path(path)
    assert isinstance(normalized, str)
    # the exact value depends on the OS, but it should be a string and resolve

def test_start_service_win32():
    abstractor = PlatformAbstractor()
    abstractor.os_type = "win32"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = abstractor.start_service("test_service")
        assert result is True
        mock_run.assert_called_once_with(["sc", "start", "test_service"], check=True, capture_output=True)

def test_start_service_darwin():
    abstractor = PlatformAbstractor()
    abstractor.os_type = "darwin"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = abstractor.start_service("test_service")
        assert result is True
        mock_run.assert_called_once_with(["launchctl", "start", "test_service"], check=True, capture_output=True)

def test_start_service_linux():
    abstractor = PlatformAbstractor()
    abstractor.os_type = "linux"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = abstractor.start_service("test_service")
        assert result is True
        mock_run.assert_called_once_with(["systemctl", "start", "test_service"], check=True, capture_output=True)

def test_stop_service_win32():
    abstractor = PlatformAbstractor()
    abstractor.os_type = "win32"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = abstractor.stop_service("test_service")
        assert result is True
        mock_run.assert_called_once_with(["sc", "stop", "test_service"], check=True, capture_output=True)

def test_restart_service_win32():
    abstractor = PlatformAbstractor()
    abstractor.os_type = "win32"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = abstractor.restart_service("test_service")
        assert result is True
        mock_run.assert_called_once_with(["powershell", "-Command", "Restart-Service -Name test_service"], check=True, capture_output=True)

def test_service_status_win32():
    abstractor = PlatformAbstractor()
    abstractor.os_type = "win32"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="Running", returncode=0)
        result = abstractor.service_status("test_service")
        assert result == "Running"
        mock_run.assert_called_once_with(["sc", "query", "test_service"], check=True, capture_output=True, text=True)

def test_start_service_exception():
    abstractor = PlatformAbstractor()
    abstractor.os_type = "linux"
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, ["systemctl", "start", "test_service"], stderr=b"Error")
        result = abstractor.start_service("test_service")
        assert result is False
