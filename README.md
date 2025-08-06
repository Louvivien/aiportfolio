# AI Portfolio Tracker

![Python](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/fastapi-0.95.2-green)
![Streamlit](https://img.shields.io/badge/streamlit-1.24-orange)

## 🚀 Project Overview

A self-hosted portfolio tracker with:
- Tagging and theme roll-ups
- Live price fetching (Yahoo Finance)
- Streamlit front-end

## 🛠️ Prerequisites

- macOS, Python 3.13+, MongoDB Atlas account
- [Node.js & npm] if you later add React

## 🔧 Setup

git clone https://github.com/Louvivien/aiportfolio.git
cd aiportfolio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt


## 🏃‍♂️ Running

Backend

uvicorn backend.app.main:app --reload

Frontend (Streamlit)

cd frontend
streamlit run app.py

## ✅ Testing

Unit & CRUD tests:

pytest backend/tests -q

E2E (Playwright):

pytest frontend/tests -q

🧹 Linting & Formatting

We use pre-commit with:

black

isort

flake8

To install Git hooks:

pre-commit install

Run them manually:

pre-commit run --all-files


## 📚 Documentation

Automatic API docs via FastAPI at /docs and /redoc

Inline docstrings in backend/app/*.py

## 🤝 Contributing

Fork & branch: git checkout -b feature/XYZ

Commit with clear messages

Open a PR with this template:

What you did

Why it matters

Screenshots (if UI)

Link related Jira ticket
