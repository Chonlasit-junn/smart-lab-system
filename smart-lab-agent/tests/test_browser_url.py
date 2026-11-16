import io
import sys
import threading
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
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

    def test_website_rules_detect_com_and_net_domains_from_browser_urls(self):
        rules = normalize_rules([
            {"id": 3, "app_name": "Blocked .com", "match_type": "website_domain",
             "match_value": "blocked.com", "enabled": True},
            {"id": 4, "app_name": "Blocked .net", "match_type": "website_domain",
             "match_value": "blocked.net", "enabled": True},
        ])
        for url, expected_rule_id in (
            ("https://www.blocked.com/path?q=private", 3),
            ("https://sub.blocked.net/", 4),
        ):
            domain = browser_url.normalize_domain(url)
            with self.subTest(url=url):
                self.assertEqual(find_website_match(rules, domain)["id"], expected_rule_id)

    def test_website_rules_do_not_match_executable_identity(self):
        self.assertIsNone(find_process_match(self.rules, "example.com.exe",
                                            executable_identity={"original_filename": "example.com.exe"}))

    def test_known_browser_executable_identity_is_required(self):
        for original in ("chrome.exe", "msedge.exe"):
            self.assertTrue(browser_url.browser_name({"original_filename": original}))
        self.assertIsNone(browser_url.browser_name({"original_filename": "notepad.exe", "product_name": "Chrome"}))

    def test_recognizes_major_browser_families_and_unknown_browser_products(self):
        for original in (
            "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
            "vivaldi.exe", "arc.exe", "librewolf.exe", "waterfox.exe", "floorp.exe",
            "palemoon.exe", "maxthon.exe", "360chrome.exe", "qqbrowser.exe",
            "baidubrowser.exe", "duckduckgo.exe", "coccoc.exe", "yandex.exe",
        ):
            with self.subTest(original=original):
                self.assertIsNotNone(browser_url.browser_name({"original_filename": original}))

        self.assertEqual(
            browser_url.browser_name({"product_name": "Example Web Browser"}),
            "Example Web Browser",
        )
        self.assertEqual(
            browser_url.browser_name({}, executable_path=r"C:\Apps\Firefox\firefox.exe"),
            "Firefox",
        )
        self.assertIsNone(
            browser_url.browser_name({"product_name": "Microsoft Edge WebView2 Runtime"})
        )


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

    def test_failed_url_read_is_cleared_and_polling_recovers(self):
        monitor = self.monitor()
        failed = Future()
        failed.set_exception(RuntimeError("browser read failed"))
        next_request = Future()
        monitor.pending = failed
        monitor.executor.submit.return_value = next_request

        with patch.object(browser_url, "foreground_window", return_value=42):
            self.assertIsNone(monitor.poll())

        self.assertIs(monitor.pending, next_request)
        monitor.executor.submit.assert_called_once()

    def test_closed_monitor_does_not_schedule_work(self):
        monitor = self.monitor()
        monitor.closed = True
        with patch.object(browser_url, "foreground_window", return_value=42):
            monitor.poll()
        monitor.executor.submit.assert_not_called()

    def test_generic_chromium_window_class_is_recognized(self):
        def get_class_name(_window, output, _capacity):
            output.value = "Chrome_WidgetWin_1"
            return len(output.value)

        user32 = SimpleNamespace(GetClassNameW=get_class_name)
        with patch.object(browser_url.os, "name", "nt"), patch.object(
            browser_url.ctypes, "WinDLL", return_value=user32,
        ):
            self.assertTrue(browser_url.is_browser_window(42))

    def test_browser_window_class_allows_reader_for_unrecognized_browser_binary(self):
        process = SimpleNamespace(
            pid=123,
            exe=Mock(return_value=r"C:\Apps\ExampleBrowser\app.exe"),
            name=Mock(return_value="app.exe"),
        )
        helper = SimpleNamespace(
            poll=Mock(return_value=None),
            kill=Mock(),
            stdin=io.StringIO(),
            stdout=io.StringIO('{"value":"https://blocked.example/path"}\n'),
        )
        reader = browser_url.BrowserURLReader.__new__(browser_url.BrowserURLReader)
        reader._process = helper
        reader._lock = threading.Lock()
        reader._closed = False

        with patch.object(browser_url.os, "name", "nt"), patch.object(
            browser_url, "window_process", return_value=process,
        ), patch.object(browser_url, "read_executable_identity", return_value={}), patch.object(
            browser_url, "is_browser_window", return_value=True,
        ):
            observation = reader.read(42)

        self.assertEqual(observation["domain"], "blocked.example")

    def test_warning_rechecks_original_window_not_foreground_dialog(self):
        monitor = self.monitor()
        future = Future()
        future.set_result({"domain": "example.com"})
        monitor.executor.submit.return_value = future
        self.assertEqual(monitor.recheck({"browser_hwnd": 42, "browser_pid": 123})["domain"], "example.com")
        monitor.executor.submit.assert_called_once_with(monitor.reader.read, 42, 123)
