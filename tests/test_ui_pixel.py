"""Browser pixel check: the app boots and renders in real Chromium.

Runs in CI (Playwright + Chromium installed on the runner). Skips
locally when Playwright is absent so the repo stays storage-light —
no browser is ever downloaded to the developer machine for this.

Requires the API on http://127.0.0.1:8000 (CI starts it first).
Asserts: 13 workflow tabs present, snapshot metrics render, no
blank-page failure, and saves a screenshot artifact.
"""

import os
import sys
import tempfile
import unittest

BASE = os.environ.get("TRIALNEXUS_BASE_URL", "http://127.0.0.1:8000")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

GATED = (
    sync_playwright is None
    or os.environ.get("TRIALNEXUS_BROWSER_TEST") != "1"
)


@unittest.skipIf(GATED, "browser-gated (CI pixel job sets TRIALNEXUS_BROWSER_TEST=1)")
class PixelTests(unittest.TestCase):
    def test_app_renders_in_chromium(self):
        errors = []
        with sync_playwright() as p:
            channel = os.environ.get("PLAYWRIGHT_CHANNEL") or None
            browser = p.chromium.launch(channel=channel)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda err: errors.append(err))
            # domcontentloaded: boot fires heavy panels (sweep/twins), so
            # networkidle never settles; targeted waits below assert renders.
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_selector("#snapshot .metric", timeout=30000)
            tabs = page.query_selector_all("[id^='tabbtn-']")
            self.assertEqual(len(tabs), 13)
            metrics = page.inner_text("#snapshot")
            for label in ("Protocols", "Sites", "FHIR patients"):
                self.assertIn(label, metrics)
            self.assertIn("API online", page.inner_text("#apiStatus"))
            # Cohort tab renders verdicts, not a blank panel (detail
            # tables are collapsed by design: attached, not visible).
            page.click("#tabbtn-cohort")
            page.wait_for_selector(
                "#cohortResult table", timeout=30000, state="attached"
            )
            page.wait_for_selector("#cohortResult .badge", timeout=30000)
            shot_dir = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
            shot = os.path.join(shot_dir, "pixel_proof.png")
            page.screenshot(path=shot)
            browser.close()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    sys.exit(unittest.main())
