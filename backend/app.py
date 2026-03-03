"""
app.py – Flask REST API server for BalanceMate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from tracker import ActivityTracker, SuggestionEngine, SummaryGenerator

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR)
CORS(app)

tracker = ActivityTracker()
suggestion_engine = SuggestionEngine(tracker)
summary_generator = SummaryGenerator(tracker)


# ── Static Frontend ──────────────────────────────────────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(app.static_folder, path)


# ── Activity ──────────────────────────────────────────────────────────────────

@app.route("/api/activity", methods=["POST"])
def log_activity():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(tracker.log_activity(data))


# ── Suggestions ───────────────────────────────────────────────────────────────

@app.route("/api/suggestions", methods=["GET"])
def get_suggestions():
    user_id = request.args.get("user_id", "default")
    return jsonify(suggestion_engine.get_suggestions(user_id))


@app.route("/api/suggestions/respond", methods=["POST"])
def respond_to_suggestion():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id", "default")
    suggestion_type = data.get("suggestion_type", "")
    accepted = bool(data.get("accepted", False))
    return jsonify(
        suggestion_engine.log_suggestion_response(user_id, suggestion_type, accepted)
    )


# ── Summary ───────────────────────────────────────────────────────────────────

@app.route("/api/summary", methods=["GET"])
def get_summary():
    user_id = request.args.get("user_id", "default")
    date = request.args.get("date") or None
    return jsonify(summary_generator.get_daily_summary(user_id, date))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    user_id = request.args.get("user_id", "default")
    return jsonify(tracker.get_dashboard_data(user_id))


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/api/settings", methods=["GET"])
def get_settings():
    user_id = request.args.get("user_id", "default")
    return jsonify(tracker.get_preferences(user_id))


@app.route("/api/settings", methods=["POST"])
def update_settings():
    user_id = request.args.get("user_id", "default")
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(tracker.update_preferences(user_id, data))


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "BalanceMate"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
