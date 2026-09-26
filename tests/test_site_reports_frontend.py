from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SiteReportsTabFrontendTests(unittest.TestCase):
    def _html(self):
        return (ROOT / "admin" / "index.html").read_text(encoding="utf-8")

    def test_site_reports_use_tabbed_sections(self):
        html = self._html()
        self.assertEqual(html.count('class="site-report-tabs"'), 1)
        for tab in ("overview", "source", "content", "crawler", "logs"):
            self.assertIn(f'data-report-tab="{tab}"', html)
            self.assertIn(f'data-site-report-tab="{tab}"', html)
            self.assertIn(f"switchSiteReportTab('{tab}')", html)

    def test_site_reports_keep_all_data_sections(self):
        html = self._html()
        # 各标签页仍保留原有数据区块，避免折叠时丢失功能
        for element_id in (
            "siteReportKpiGrid", "siteReportTrend", "siteAiReportCard",
            "siteReportProvinceBody", "siteReportContinentBody",
            "siteReportSourceBody", "siteReportDeviceBody",
            "siteReportOsBody", "siteReportCountryBody",
            "siteReportPromotionBody", "siteReportCrawlerBody",
            "siteReportPagesBody", "siteReportEventsBody",
            "siteReportRecentBody", "adminLoginLogsBody",
        ):
            self.assertIn(f'id="{element_id}"', html)

    def test_switch_site_report_tab_defined(self):
        script = (ROOT / "admin" / "js" / "site-report-ui.js").read_text(encoding="utf-8")
        self.assertIn("window.switchSiteReportTab = switchSiteReportTab", script)


if __name__ == "__main__":
    unittest.main()
