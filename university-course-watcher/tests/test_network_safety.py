from __future__ import annotations

import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.network_safety import SafeHttpSession, UnsafeUrlError, require_public_http_url


class NetworkSafetyTest(unittest.TestCase):
    def test_hostname_resolving_to_private_address_is_rejected(self) -> None:
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]

        with patch("src.network_safety.socket.getaddrinfo", return_value=resolved):
            with self.assertRaisesRegex(UnsafeUrlError, "Non-public IP"):
                require_public_http_url("https://attacker.example/file.pdf", resolve_host=True)

    def test_public_hostname_is_accepted(self) -> None:
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

        with patch("src.network_safety.socket.getaddrinfo", return_value=resolved):
            self.assertEqual(
                "https://university.example/notice",
                require_public_http_url("https://university.example/notice", resolve_host=True),
            )

    def test_session_revalidates_every_prepared_request_including_redirects(self) -> None:
        session = SafeHttpSession()
        initial = requests.Request("GET", "https://public.example/start").prepare()
        redirected = requests.Request("GET", "http://127.0.0.1/internal").prepare()
        response = Mock(spec=requests.Response)

        with patch("src.network_safety.socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ]), patch("requests.Session.send", return_value=response) as parent_send:
            self.assertIs(response, session.send(initial))
            parent_send.assert_called_once()

        with self.assertRaisesRegex(UnsafeUrlError, "Non-public IP"):
            session.send(redirected)
