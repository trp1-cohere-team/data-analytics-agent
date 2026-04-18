#!/bin/bash
cd /home/nurye/data-analytics-agent
pip install fastapi uvicorn -q
python -m uvicorn app.api:app --host 0.0.0.0 --port 8501 --reload
