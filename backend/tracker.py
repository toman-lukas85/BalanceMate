"""
tracker.py – Core activity tracking, suggestion engine, and summary generation.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "balancemate.db")

DEFAULT_PREFERENCES: Dict[str, Any] = {
    "short_break_interval_min": 25,
    "long_break_interval_min": 90,
    "short_break_duration_min": 5,
    "long_break_duration_min": 15,
    "focus_session_target_min": 50,
    "context_switch_threshold": 10,
    "work_start_hour": 9,
    "work_end_hour": 18,
    "notifications_enabled": True,
    "user_name": "User",
    "work_style": "balanced",  # 'deep-focus' | 'collaborative' | 'balanced'
}


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS activities (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          TEXT    NOT NULL,
            timestamp        TEXT    NOT NULL,
            activity_type    TEXT    NOT NULL,
            duration_seconds INTEGER DEFAULT 0,
            metadata         TEXT    DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS preferences (
            user_id   TEXT NOT NULL,
            pref_key  TEXT NOT NULL,
            pref_value TEXT NOT NULL,
            PRIMARY KEY (user_id, pref_key)
        );

        CREATE TABLE IF NOT EXISTS suggestions_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT    NOT NULL,
            timestamp       TEXT    NOT NULL,
            suggestion_type TEXT    NOT NULL,
            message         TEXT    NOT NULL,
            accepted        INTEGER DEFAULT 0
        );
        """
    )
    conn.commit()
    conn.close()


class ActivityTracker:
    """Tracks work sessions, window switches, and break events."""

    def __init__(self) -> None:
        init_db()
        # In-memory session state keyed by user_id
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    #  Activity Logging                                                    #
    # ------------------------------------------------------------------ #

    def log_activity(self, data: Dict[str, Any]) -> Dict[str, Any]:
        user_id = data.get("user_id", "default")
        activity_type = data.get("type", "heartbeat")
        duration = int(data.get("duration_seconds", 0))
        metadata = json.dumps(data.get("metadata", {}))
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        conn = get_db()
        conn.execute(
            "INSERT INTO activities "
            "(user_id, timestamp, activity_type, duration_seconds, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, timestamp, activity_type, duration, metadata),
        )
        conn.commit()
        conn.close()

        self._update_active_session(user_id, activity_type)
        return {"status": "logged", "timestamp": timestamp, "type": activity_type}

    def _update_active_session(self, user_id: str, activity_type: str) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if user_id not in self._active_sessions:
            self._active_sessions[user_id] = {
                "start_time": now,
                "last_activity": now,
                "window_switches": 0,
                "session_type": "work",
            }
        session = self._active_sessions[user_id]
        session["last_activity"] = now

        if activity_type == "window_switch":
            session["window_switches"] = session.get("window_switches", 0) + 1
        elif activity_type == "break_start":
            session["session_type"] = "break"
        elif activity_type in ("break_end", "session_start"):
            session["session_type"] = "work"
            session["start_time"] = now
            session["window_switches"] = 0

    # ------------------------------------------------------------------ #
    #  Session State                                                       #
    # ------------------------------------------------------------------ #

    def get_current_session(self, user_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if user_id not in self._active_sessions:
            return {
                "duration_seconds": 0,
                "session_type": "idle",
                "window_switches": 0,
                "start_time": now.isoformat(),
            }
        session = self._active_sessions[user_id]
        elapsed = int((now - session["start_time"]).total_seconds())
        return {
            "duration_seconds": max(elapsed, 0),
            "session_type": session.get("session_type", "work"),
            "window_switches": session.get("window_switches", 0),
            "start_time": session["start_time"].isoformat(),
        }

    # ------------------------------------------------------------------ #
    #  Dashboard                                                           #
    # ------------------------------------------------------------------ #

    def get_dashboard_data(self, user_id: str) -> Dict[str, Any]:
        today = datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()
        conn = get_db()
        activities = conn.execute(
            "SELECT * FROM activities "
            "WHERE user_id = ? AND DATE(timestamp) = ? "
            "ORDER BY timestamp",
            (user_id, today),
        ).fetchall()
        conn.close()

        # Hourly breakdown (seconds of tracked activity per hour)
        hourly_work = [0] * 24
        for act in activities:
            if act["activity_type"] in ("break_start", "break_end"):
                continue
            try:
                ts = datetime.fromisoformat(act["timestamp"])
                hourly_work[ts.hour] += max(int(act["duration_seconds"]), 1)
            except (ValueError, TypeError):
                pass

        total_work_seconds = sum(
            int(a["duration_seconds"])
            for a in activities
            if a["activity_type"] not in ("break_start", "break_end", "window_switch")
        )
        total_switches = sum(
            1 for a in activities if a["activity_type"] == "window_switch"
        )
        session_starts = sum(
            1 for a in activities if a["activity_type"] == "session_start"
        )

        return {
            "current_session": self.get_current_session(user_id),
            "today": {
                "total_work_minutes": round(total_work_seconds / 60, 1),
                "window_switches": total_switches,
                "sessions_count": max(session_starts, 1),
            },
            "hourly_breakdown": hourly_work,
            "preferences": self.get_preferences(user_id),
        }

    # ------------------------------------------------------------------ #
    #  Preferences                                                         #
    # ------------------------------------------------------------------ #

    def get_preferences(self, user_id: str) -> Dict[str, Any]:
        conn = get_db()
        rows = conn.execute(
            "SELECT pref_key, pref_value FROM preferences WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        conn.close()

        prefs: Dict[str, Any] = dict(DEFAULT_PREFERENCES)
        for row in rows:
            key, raw = row["pref_key"], row["pref_value"]
            if key in prefs:
                try:
                    prefs[key] = json.loads(raw)
                except json.JSONDecodeError:
                    prefs[key] = raw
        return prefs

    def update_preferences(self, user_id: str, new_prefs: Dict[str, Any]) -> Dict[str, Any]:
        conn = get_db()
        for key, value in new_prefs.items():
            if key in DEFAULT_PREFERENCES:
                conn.execute(
                    "INSERT OR REPLACE INTO preferences "
                    "(user_id, pref_key, pref_value) VALUES (?, ?, ?)",
                    (user_id, key, json.dumps(value)),
                )
        conn.commit()
        conn.close()
        return self.get_preferences(user_id)

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def get_recent_activities(self, user_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)).isoformat()
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM activities "
            "WHERE user_id = ? AND timestamp >= ? "
            "ORDER BY timestamp DESC",
            (user_id, since),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class SuggestionEngine:
    """Generates AI-style break and focus recommendations based on work patterns."""

    def __init__(self, tracker: ActivityTracker) -> None:
        self.tracker = tracker

    def get_suggestions(self, user_id: str) -> Dict[str, Any]:
        session = self.tracker.get_current_session(user_id)
        prefs = self.tracker.get_preferences(user_id)

        suggestions: List[Dict[str, Any]] = []
        urgency = "normal"

        duration_min = session["duration_seconds"] / 60
        switches = session.get("window_switches", 0)
        session_type = session.get("session_type", "work")

        short_interval = prefs.get("short_break_interval_min", 25)
        long_interval = prefs.get("long_break_interval_min", 90)
        switch_threshold = prefs.get("context_switch_threshold", 10)
        short_dur = prefs.get("short_break_duration_min", 5)
        long_dur = prefs.get("long_break_duration_min", 15)

        if session_type == "work":
            if duration_min >= long_interval:
                urgency = "high"
                suggestions.append(
                    {
                        "type": "long_break",
                        "message": (
                            f"You've been working for {int(duration_min)} minutes. "
                            f"Take a {long_dur}-minute break to restore focus and prevent fatigue."
                        ),
                        "duration_min": long_dur,
                        "icon": "🌿",
                    }
                )
            elif duration_min >= short_interval:
                urgency = "medium"
                suggestions.append(
                    {
                        "type": "short_break",
                        "message": (
                            f"You've been working for {int(duration_min)} minutes. "
                            f"A quick {short_dur}-minute break will help maintain your focus."
                        ),
                        "duration_min": short_dur,
                        "icon": "☕",
                    }
                )

            if switches >= switch_threshold:
                urgency = urgency if urgency != "normal" else "medium"
                suggestions.append(
                    {
                        "type": "focus_mode",
                        "message": (
                            f"You've switched contexts {switches} times. "
                            "Try a focused work block — close unnecessary tabs and notifications."
                        ),
                        "icon": "🎯",
                    }
                )

            if duration_min < 10 and not suggestions:
                suggestions.append(
                    {
                        "type": "deep_work",
                        "message": (
                            "Great start! Aim for a 25-minute focused work block "
                            "to enter a flow state."
                        ),
                        "icon": "🚀",
                    }
                )
        elif session_type == "break":
            suggestions.append(
                {
                    "type": "break_active",
                    "message": "Enjoy your break! Step away from the screen if possible.",
                    "icon": "😊",
                }
            )

        if not suggestions:
            suggestions.append(
                {
                    "type": "on_track",
                    "message": "You're doing great! Keep up the balanced work rhythm.",
                    "icon": "✅",
                }
            )

        return {
            "suggestions": suggestions,
            "urgency": urgency,
            "session": session,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

    def log_suggestion_response(
        self, user_id: str, suggestion_type: str, accepted: bool
    ) -> Dict[str, Any]:
        conn = get_db()
        conn.execute(
            "INSERT INTO suggestions_log "
            "(user_id, timestamp, suggestion_type, message, accepted) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                user_id,
                datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                suggestion_type,
                "",
                int(accepted),
            ),
        )
        conn.commit()
        conn.close()
        return {"status": "logged"}


class SummaryGenerator:
    """Generates daily AI-driven summaries with actionable insights."""

    def __init__(self, tracker: ActivityTracker) -> None:
        self.tracker = tracker

    def get_daily_summary(
        self, user_id: str, date: Optional[str] = None
    ) -> Dict[str, Any]:
        if date is None:
            date = datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()

        conn = get_db()
        activities = conn.execute(
            "SELECT * FROM activities "
            "WHERE user_id = ? AND DATE(timestamp) = ? "
            "ORDER BY timestamp",
            (user_id, date),
        ).fetchall()
        conn.close()

        if not activities:
            return {
                "date": date,
                "message": "No activity recorded for this day.",
                "stats": {},
                "insights": [],
            }

        total_duration = sum(int(a["duration_seconds"]) for a in activities)
        break_count = sum(1 for a in activities if a["activity_type"] == "break_start")
        switch_count = sum(1 for a in activities if a["activity_type"] == "window_switch")
        work_minutes = round(total_duration / 60, 1)

        return {
            "date": date,
            "stats": {
                "total_work_minutes": work_minutes,
                "break_count": break_count,
                "window_switches": switch_count,
                "activity_count": len(activities),
                "focus_score": self._calculate_focus_score(
                    work_minutes, break_count, switch_count
                ),
            },
            "insights": self._generate_insights(work_minutes, break_count, switch_count),
            "message": self._generate_summary_message(
                work_minutes, break_count, switch_count
            ),
        }

    def _calculate_focus_score(
        self, work_minutes: float, break_count: int, switch_count: int
    ) -> int:
        score = 70
        if 120 <= work_minutes <= 360:
            score += 10
        elif work_minutes > 480:
            score -= 15
        if 3 <= break_count <= 8:
            score += 10
        elif break_count == 0:
            score -= 20
        elif break_count > 12:
            score -= 10
        if switch_count < 20:
            score += 10
        elif switch_count > 50:
            score -= 15
        return max(0, min(100, score))

    def _generate_insights(
        self, work_minutes: float, break_count: int, switch_count: int
    ) -> List[str]:
        insights: List[str] = []

        if work_minutes > 480:
            insights.append(
                "⚠️ You worked over 8 hours today. "
                "Consider setting hard boundaries to prevent burnout."
            )
        elif work_minutes < 120:
            insights.append(
                "💡 Short workday detected. "
                "If intentional, great! If not, try scheduling focused blocks."
            )
        else:
            insights.append(
                f"✅ You logged {int(work_minutes)} minutes of work today — a solid effort!"
            )

        if break_count == 0:
            insights.append(
                "⚠️ No breaks detected today. "
                "Regular breaks are essential for sustained focus and well-being."
            )
        elif break_count < 3:
            insights.append(
                "💡 You took only a few breaks. "
                "Try the 25/5 Pomodoro rhythm for better focus."
            )
        else:
            insights.append(
                f"✅ You took {break_count} breaks today — good habit for maintaining energy!"
            )

        if switch_count > 50:
            insights.append(
                "⚠️ High context switching detected. "
                "Try batching similar tasks to reduce cognitive load."
            )
        elif switch_count < 10:
            insights.append(
                "✅ Low context switching suggests good focus periods today."
            )

        return insights

    def _generate_summary_message(
        self, work_minutes: float, break_count: int, switch_count: int
    ) -> str:
        if work_minutes == 0:
            return "No work sessions recorded today."

        if break_count == 0 or work_minutes > 600:
            quality = "intense"
        elif break_count >= 3 and work_minutes <= 480:
            quality = "well-balanced"
        elif switch_count > 50:
            quality = "fragmented"
        else:
            quality = "excellent"

        messages = {
            "excellent": (
                "Outstanding work-life balance today! "
                "Your work rhythm shows great focus with healthy recovery periods."
            ),
            "well-balanced": (
                "Good balance today! "
                "You maintained steady work sessions with appropriate breaks."
            ),
            "intense": (
                "Intense work day detected. "
                "Make sure to fully recharge this evening — rest is part of performance."
            ),
            "fragmented": (
                "Today showed high task-switching. "
                "Tomorrow, try blocking focused time to reduce cognitive overhead."
            ),
        }
        return messages.get(quality, messages["well-balanced"])
