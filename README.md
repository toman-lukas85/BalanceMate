# BalanceMate

> An AI-driven personal work–life balance coach for modern knowledge workers.

## Overview

BalanceMate continuously analyzes your work activity — typing patterns, window
switching, and session length — to detect fatigue and cognitive overload in real
time. It provides smart recommendations for breaks, deep-work blocks, and
recovery, generates daily AI-driven summaries with actionable insights, and
adapts to each user's unique rhythm.

## Features

- **Activity Tracker** – Monitors work sessions, break patterns, and context switches
- **AI Break & Focus Suggestions** – Smart recommendations based on your work rhythm
- **Daily Summary** – AI-generated insights with a Focus Score and actionable tips
- **Work Rhythm Dashboard** – Hourly activity chart and real-time session stats
- **Personalization** – Customize break intervals, focus targets, and work style

## Getting Started

### Prerequisites

- Python 3.8+

### Installation

```bash
cd backend
pip install -r requirements.txt
```

### Running the App

```bash
cd backend
python app.py
```

Then open [http://localhost:5000](http://localhost:5000) in your browser.

### Running Tests

```bash
python -m pytest tests/test_tracker.py -v
```

## Project Structure

```
BalanceMate/
├── backend/
│   ├── app.py           # Flask REST API server
│   ├── tracker.py       # Core activity tracking & AI analysis
│   └── requirements.txt
├── frontend/
│   ├── index.html       # Dashboard UI
│   ├── css/
│   │   └── styles.css
│   └── js/
│       └── app.js
└── tests/
    └── test_tracker.py
```

## API Endpoints

| Method | Endpoint                  | Description                         |
|--------|---------------------------|-------------------------------------|
| POST   | `/api/activity`           | Log an activity event               |
| GET    | `/api/suggestions`        | Get current AI recommendations      |
| POST   | `/api/suggestions/respond`| Record user response to suggestion  |
| GET    | `/api/summary`            | Get daily summary                   |
| GET    | `/api/dashboard`          | Get dashboard data                  |
| GET    | `/api/settings`           | Get user preferences                |
| POST   | `/api/settings`           | Update user preferences             |
| GET    | `/api/health`             | Health check                        |

## Tech Stack

- **Backend**: Python, Flask, SQLite
- **Frontend**: HTML5, CSS3, Vanilla JavaScript, Chart.js
