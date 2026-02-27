#!/bin/bash
# Render deployment start script
gunicorn sales_dashboard:server -w 2 --bind 0.0.0.0:$PORT
