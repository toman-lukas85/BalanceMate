"""
test_tracker.py – Unit tests for backend/tracker.py
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

# Ensure backend module is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Redirect the SQLite database to a temporary file so tests don't touch
# the real database on disk.
import tracker as tracker_module  # noqa: E402 – import after path setup

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
tracker_module.DATABASE_PATH = _tmp_db.name
tracker_module.init_db()

from tracker import ActivityTracker, SuggestionEngine, SummaryGenerator  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# ActivityTracker
# ─────────────────────────────────────────────────────────────────────────────


class TestActivityTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = ActivityTracker()

    # -- log_activity ----------------------------------------------------------

    def test_log_activity_returns_logged_status(self):
        result = self.tracker.log_activity(
            {"user_id": "u1", "type": "heartbeat", "duration_seconds": 30}
        )
        self.assertEqual(result["status"], "logged")
        self.assertEqual(result["type"], "heartbeat")
        self.assertIn("timestamp", result)

    def test_log_activity_uses_default_user_id(self):
        result = self.tracker.log_activity({"type": "heartbeat"})
        self.assertEqual(result["status"], "logged")

    # -- get_current_session ---------------------------------------------------

    def test_get_current_session_idle_for_unknown_user(self):
        session = self.tracker.get_current_session("unknown_xyz_user")
        self.assertEqual(session["session_type"], "idle")
        self.assertEqual(session["duration_seconds"], 0)

    def test_session_type_becomes_break_after_break_start(self):
        uid = "break_test"
        self.tracker.log_activity({"user_id": uid, "type": "session_start"})
        self.tracker.log_activity({"user_id": uid, "type": "break_start"})
        session = self.tracker.get_current_session(uid)
        self.assertEqual(session["session_type"], "break")

    def test_session_type_returns_to_work_after_break_end(self):
        uid = "break_end_test"
        self.tracker.log_activity({"user_id": uid, "type": "session_start"})
        self.tracker.log_activity({"user_id": uid, "type": "break_start"})
        self.tracker.log_activity({"user_id": uid, "type": "break_end"})
        session = self.tracker.get_current_session(uid)
        self.assertEqual(session["session_type"], "work")

    def test_window_switches_are_counted(self):
        uid = "switch_test"
        self.tracker.log_activity({"user_id": uid, "type": "session_start"})
        self.tracker.log_activity({"user_id": uid, "type": "window_switch"})
        self.tracker.log_activity({"user_id": uid, "type": "window_switch"})
        session = self.tracker.get_current_session(uid)
        self.assertEqual(session["window_switches"], 2)

    def test_window_switches_reset_after_break_end(self):
        uid = "switch_reset_test"
        self.tracker.log_activity({"user_id": uid, "type": "session_start"})
        self.tracker.log_activity({"user_id": uid, "type": "window_switch"})
        self.tracker.log_activity({"user_id": uid, "type": "break_end"})
        session = self.tracker.get_current_session(uid)
        self.assertEqual(session["window_switches"], 0)

    # -- get_dashboard_data ----------------------------------------------------

    def test_dashboard_data_has_required_keys(self):
        uid = "dashboard_test"
        self.tracker.log_activity(
            {"user_id": uid, "type": "heartbeat", "duration_seconds": 60}
        )
        data = self.tracker.get_dashboard_data(uid)
        self.assertIn("current_session", data)
        self.assertIn("today", data)
        self.assertIn("hourly_breakdown", data)
        self.assertIn("preferences", data)
        self.assertEqual(len(data["hourly_breakdown"]), 24)

    # -- preferences -----------------------------------------------------------

    def test_default_preferences_are_returned_for_new_user(self):
        prefs = self.tracker.get_preferences("brand_new_user_xyz")
        self.assertEqual(prefs["short_break_interval_min"], 25)
        self.assertEqual(prefs["long_break_interval_min"], 90)
        self.assertIn("user_name", prefs)
        self.assertIn("work_style", prefs)

    def test_update_preferences_persists_values(self):
        uid = "prefs_update_test"
        self.tracker.update_preferences(
            uid, {"short_break_interval_min": 30, "user_name": "Alice"}
        )
        prefs = self.tracker.get_preferences(uid)
        self.assertEqual(prefs["short_break_interval_min"], 30)
        self.assertEqual(prefs["user_name"], "Alice")

    def test_update_preferences_ignores_unknown_keys(self):
        uid = "prefs_unknown_test"
        self.tracker.update_preferences(uid, {"nonexistent_key": "value"})
        prefs = self.tracker.get_preferences(uid)
        self.assertNotIn("nonexistent_key", prefs)

    # -- get_recent_activities -------------------------------------------------

    def test_get_recent_activities_returns_list(self):
        uid = "recent_test"
        self.tracker.log_activity(
            {"user_id": uid, "type": "heartbeat", "duration_seconds": 10}
        )
        activities = self.tracker.get_recent_activities(uid, hours=1)
        self.assertIsInstance(activities, list)
        self.assertGreaterEqual(len(activities), 1)

    def test_get_recent_activities_empty_for_old_data(self):
        uid = "recent_old_data"
        # No activity logged – looking 0 hours back should return nothing
        activities = self.tracker.get_recent_activities(uid, hours=0)
        self.assertEqual(activities, [])


# ─────────────────────────────────────────────────────────────────────────────
# SuggestionEngine
# ─────────────────────────────────────────────────────────────────────────────


class TestSuggestionEngine(unittest.TestCase):
    def setUp(self):
        self.tracker = ActivityTracker()
        self.engine = SuggestionEngine(self.tracker)

    def test_get_suggestions_returns_correct_structure(self):
        result = self.engine.get_suggestions("suggest_test")
        self.assertIn("suggestions", result)
        self.assertIn("urgency", result)
        self.assertIn("session", result)
        self.assertIn("timestamp", result)
        self.assertIsInstance(result["suggestions"], list)
        self.assertGreater(len(result["suggestions"]), 0)

    def test_fresh_session_does_not_trigger_break_suggestion(self):
        uid = "fresh_user"
        self.tracker.log_activity({"user_id": uid, "type": "session_start"})
        result = self.engine.get_suggestions(uid)
        types = [s["type"] for s in result["suggestions"]]
        self.assertNotIn("short_break", types)
        self.assertNotIn("long_break", types)

    def test_break_active_suggestion_shown_during_break(self):
        uid = "break_active_user"
        self.tracker.log_activity({"user_id": uid, "type": "session_start"})
        self.tracker.log_activity({"user_id": uid, "type": "break_start"})
        result = self.engine.get_suggestions(uid)
        types = [s["type"] for s in result["suggestions"]]
        self.assertIn("break_active", types)

    def test_log_suggestion_response_accepted(self):
        result = self.engine.log_suggestion_response("u1", "short_break", True)
        self.assertEqual(result["status"], "logged")

    def test_log_suggestion_response_dismissed(self):
        result = self.engine.log_suggestion_response("u1", "short_break", False)
        self.assertEqual(result["status"], "logged")

    def test_each_suggestion_has_type_message_icon(self):
        uid = "structure_check"
        self.tracker.log_activity({"user_id": uid, "type": "session_start"})
        result = self.engine.get_suggestions(uid)
        for suggestion in result["suggestions"]:
            self.assertIn("type", suggestion)
            self.assertIn("message", suggestion)
            self.assertIn("icon", suggestion)


# ─────────────────────────────────────────────────────────────────────────────
# SummaryGenerator
# ─────────────────────────────────────────────────────────────────────────────


class TestSummaryGenerator(unittest.TestCase):
    def setUp(self):
        self.tracker = ActivityTracker()
        self.generator = SummaryGenerator(self.tracker)

    def test_summary_no_activity_message(self):
        result = self.generator.get_daily_summary("empty_user", "2000-01-01")
        self.assertEqual(result["date"], "2000-01-01")
        self.assertIn("message", result)
        self.assertEqual(result["stats"], {})
        self.assertEqual(result["insights"], [])

    def test_summary_with_activity_has_stats_and_insights(self):
        uid = "summary_activity_user"
        self.tracker.log_activity(
            {"user_id": uid, "type": "heartbeat", "duration_seconds": 1800}
        )
        today = datetime.now(timezone.utc).date().isoformat()
        result = self.generator.get_daily_summary(uid, today)
        self.assertIn("stats", result)
        self.assertIn("insights", result)
        self.assertIsInstance(result["insights"], list)
        self.assertGreater(len(result["insights"]), 0)

    def test_focus_score_within_valid_range(self):
        for work, breaks, switches in [
            (240, 4, 15),
            (600, 0, 60),
            (30, 1, 5),
            (0, 0, 0),
        ]:
            score = self.generator._calculate_focus_score(work, breaks, switches)
            self.assertGreaterEqual(score, 0, f"Score below 0 for ({work},{breaks},{switches})")
            self.assertLessEqual(score, 100, f"Score above 100 for ({work},{breaks},{switches})")

    def test_summary_message_intense_for_no_breaks(self):
        msg = self.generator._generate_summary_message(700, 0, 20)
        self.assertIn("intense", msg.lower())

    def test_summary_message_well_balanced(self):
        msg = self.generator._generate_summary_message(300, 5, 10)
        self.assertIn("balance", msg.lower())

    def test_insights_warn_on_no_breaks(self):
        insights = self.generator._generate_insights(300, 0, 10)
        combined = " ".join(insights).lower()
        self.assertIn("break", combined)

    def test_insights_warn_on_high_switches(self):
        insights = self.generator._generate_insights(300, 3, 60)
        combined = " ".join(insights).lower()
        self.assertIn("switch", combined)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
