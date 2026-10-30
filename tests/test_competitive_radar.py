"""Offline radar contract tests. No network and no proprietary inputs."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("radar", ROOT / "tools/competitive_radar.py")
radar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar)


class RadarTests(unittest.TestCase):
    def test_watchlist_rejects_bad_names_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "list.json"
            for raw in ('{"repositories":["a/b","a/b"]}', '{"repositories":["a/b|evil"]}'):
                path.write_text(raw)
                with self.assertRaises(radar.RadarError):
                    radar.watchlist(path)

    def test_snapshot_and_manual_note_preservation(self):
        a, b = "a" * 40, "b" * 40
        state = {"a/b": {"sha": a, "archived": False, "workflow": None}}
        body = radar.replace_section("", radar.render(["a/b"], state, {}, "2026-10-30 10:00"))
        self.assertEqual(radar.previous(body), state)
        newer = {"a/b": {**state["a/b"], "sha": b}}
        text = radar.render(["a/b"], newer, radar.previous(body), "2026-11-02 10:00")
        updated = radar.replace_section(body + "\nManual note\n", text)
        self.assertIn("Changed", updated)
        self.assertIn("Manual note", updated)
        self.assertEqual(radar.previous(updated), newer)

    def test_refuses_foreign_or_malformed_issue(self):
        for value in ("someone else's text", radar.END, radar.START + " no end"):
            with self.assertRaises(radar.RadarError):
                radar.replace_section(value, "report")

    def test_old_ci_not_claimed_at_new_head(self):
        state = {"a/b": {"sha": "a" * 40, "archived": False,
                         "workflow": {"sha": "b" * 40, "conclusion": "success"}}}
        text = radar.render(["a/b"], state, {}, "2026-10-30 10:00")
        self.assertIn("success (other SHA)", text)
        self.assertNotIn("success (exact HEAD)", text)


if __name__ == "__main__":
    unittest.main()
