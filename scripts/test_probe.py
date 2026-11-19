#!/usr/bin/env python3
"""Unit tests for Ironclad status classification and HTML honesty."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import probe

FIXED = datetime(2026, 11, 19, 7, 0, tzinfo=timezone.utc)
BRAND = {"brand": "Ironclad Sportfishing"}

WEBSITE = {"id": "website", "name": "Website", "url": "https://ironcladsportfishing.com/", "expect": [200]}
APP = {
    "id": "app",
    "name": "Crew Portal",
    "url": "https://app.ironcladsportfishing.com/",
    "expect": [200, 302, 307, 308],
}


def ok(code: int) -> dict:
    return {"status_code": code, "headers": {}, "error": None}


class ClassifyTests(unittest.TestCase):
    def test_200_is_up(self) -> None:
        self.assertEqual(probe.classify(WEBSITE, ok(200))["state"], "operational")

    def test_502_is_down(self) -> None:
        row = probe.classify(APP, ok(502))
        self.assertEqual(row["state"], "down")
        self.assertEqual(row["detail"], "HTTP 502")

    def test_redirect_to_sign_in_is_up(self) -> None:
        self.assertEqual(probe.classify(APP, ok(307))["state"], "operational")

    def test_timeout_is_check_failed_not_operational(self) -> None:
        row = probe.classify(WEBSITE, {"status_code": None, "headers": {}, "error": "TimeoutError: timed out"})
        self.assertEqual(row["state"], "error")


class RenderTests(unittest.TestCase):
    def test_app_502_is_never_shown_green(self) -> None:
        rows = [probe.classify(WEBSITE, ok(200)), probe.classify(APP, ok(502))]
        html = probe.render_html(BRAND, rows, FIXED)
        self.assertIn("Partial outage", html)
        self.assertIn("● Down", html)
        self.assertNotIn("All systems operational", html)

    def test_banner_note_is_shown_and_escaped(self) -> None:
        rows = [probe.classify(WEBSITE, ok(200))]
        html = probe.render_html(BRAND, rows, FIXED, "Booking <b>paused</b>")
        self.assertIn("Booking &lt;b&gt;paused&lt;/b&gt;", html)

    def test_entity_wall_no_dps_branding(self) -> None:
        html = probe.render_html(BRAND, [probe.classify(WEBSITE, ok(200))], FIXED)
        for banned in ("Dominion", "DPS", "PPO"):
            self.assertNotIn(banned, html)
        self.assertIn("Ironclad Sportfishing", html)

    def test_html_escapes_injected_text(self) -> None:
        row = {"id": "x", "name": "<script>alert(1)</script>", "url": "https://example.test/",
               "state": "down", "http_status": 404, "detail": "HTTP 404", "note": ""}
        html = probe.render_html(BRAND, [row], FIXED)
        self.assertNotIn("<script>alert(1)</script>", html)


class ConfigTests(unittest.TestCase):
    def test_repo_checks_are_ironclad_hosts_only(self) -> None:
        config = probe.load_checks(probe.DEFAULT_CHECKS)
        for check in config["checks"]:
            self.assertIn("ironcladsportfishing.com", check["url"])
        joined = json.dumps(config["checks"]).lower()
        self.assertNotIn("dominionprotectivesolutions", joined)
        self.assertNotIn("pitetti", joined)

    def test_repo_overrides_banner_loads(self) -> None:
        self.assertIsInstance(probe.load_banner(probe.DEFAULT_OVERRIDES), str)

    def test_missing_overrides_is_empty_banner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(probe.load_banner(Path(tmp) / "none.json"), "")

    def test_empty_checks_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checks.json"
            path.write_text(json.dumps({"checks": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                probe.load_checks(path)


if __name__ == "__main__":
    unittest.main()
