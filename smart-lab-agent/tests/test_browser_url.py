import sys
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import browser_url
from agent_policy import find_process_match, find_website_match, normalize_rules


class WebsitePolicyTests(unittest.TestCase):
    def setUp(self):
        self.rules = normalize_rules([{"id": 2, "app_name": "Example",
                                      "match_type": "website_domain", "match_value": "example.com"}])

    def test_normalizes_domain_and_discards_private_url_parts(self):
        self.assertEqual(browser_url.normalize_domain("https://EXAMPLE.com:443/private?q=secret#token"), "example.com")
        self.assertEqual(browser_url.normalize_domain("sub.example.com/path"), "sub.example.com")
        self.assertEqual(browser_url.normalize_domain("https://bücher.example/"), "xn--bcher-kva.example")

    def test_rejects_non_web_urls_search_text_and_malformed_hosts(self):
        for value in ("StarRail - Notepad", "chrome://settings", "edge://settings", "file:///secret",
                      "javascript:alert(1)", "https://user:pass@example.com", "example.com:bad",
                      "https://bad..example.com", "https://example.com\\@evil.com"):
            with self.subTest(value=value):
                self.assertIsNone(browser_url.normalize_domain(value))

    def test_matches_root_and_subdomains_but_not_lookalikes(self):
        for domain in ("example.com", "sub.example.com"):
            self.assertIsNotNone(find_website_match(self.rules, domain))
        for domain in ("example.com.evil.com", "notexample.com", "evil.com/example.com", None):
            self.assertIsNone(find_website_match(self.rules, domain))

    def test_website_rules_do_not_match_executable_identity(self):
        self.assertIsNone(find_process_match(self.rules, "example.com.exe",
                                            executable_identity={"original_filename": "example.com.exe"}))

    def test_only_supported_browser_identities_are_allowed(self):
        for original in ("chrome.exe", "msedge.exe"):
            self.assertTrue(browser_url.browser_name({"original_filename": original}))
        self.assertIsNone(browser_url.browser_name({"original_filename": "notepad.exe", "product_name": "Chrome"}))


class BrowserMonitorTests(unittest.TestCase):
    def monitor(self, result=None):
        monitor = browser_url.BrowserURLMonitor.__new__(browser_url.BrowserURLMonitor)
        monitor.reader = Mock()
        monitor.executor = Mock()
        monitor.closed = False
        monitor.pending = Future()
        monitor.pending.set_result(result)
        monitor.requested_at = time.monotonic()
        return monitor

    def test_stale_or_different_window_results_are_discarded(self):
        for age, window in ((10, 42), (0, 99)):
            monitor = self.monitor({"hwnd": 42, "domain": "example.com"})
            monitor.requested_at -= age
            with patch.object(browser_url, "foreground_window", return_value=window):
                self.assertIsNone(monitor.poll())

    def test_pending_request_is_not_duplicated(self):
        monitor = self.monitor()
        monitor.pending = Future()
        with patch.object(browser_url, "foreground_window", return_value=42):
            self.assertIsNone(monitor.poll())
        monitor.executor.submit.assert_not_called()

    def test_closed_monitor_does_not_schedule_work(self):
        monitor = self.monitor()
        monitor.closed = True
        with patch.object(browser_url, "foreground_window", return_value=42):
            monitor.poll()
        monitor.executor.submit.assert_not_called()

    def test_warning_rechecks_original_window_not_foreground_dialog(self):
        monitor = self.monitor()
        future = Future()
        future.set_result({"domain": "example.com"})
        monitor.executor.submit.return_value = future
        self.assertEqual(monitor.recheck({"browser_hwnd": 42, "browser_pid": 123})["domain"], "example.com")
        monitor.executor.submit.assert_called_once_with(monitor.reader.read, 42, 123)
