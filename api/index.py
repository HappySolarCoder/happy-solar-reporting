# -*- coding: utf-8 -*-

import json
import os
from flask import Flask, render_template_string, jsonify
from google.cloud import firestore

app = Flask(__name__)

# Try to init Firestore
db = None
try:
    # For local development
    creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if creds_json:
        import json
        from google.oauth2 import service_account
        from google.cloud import firestore
        
        creds_dict = json.loads(creds_json)
        # Write temp credentials file
        with open('/tmp/firebase-key.json', 'w') as f:
            json.dump(creds_dict, f)
        
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/tmp/firebase-key.json'
        db = firestore.Client()
except Exception as e:
    print(f"Firestore init error: {e}")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Happy Solar Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .header h1 { margin: 0; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-card h3 { margin: 0 0 10px 0; color: #666; font-size: 14px; }
        .stat-card .value { font-size: 32px; font-weight: bold; color: #333; }
    </style>
    <meta http-equiv="refresh" content="30">
</head>
<body>
    <div class="header">
        <h1>🏠 Happy Solar Sales Dashboard</h1>
        <p>Auto-refreshing every 30 seconds</p>
    </div>
    <div class="stats">
        <div class="stat-card">
            <h3>Total Contacts</h3>
            <div class="value">{{ contacts }}</div>
        </div>
        <div class="stat-card">
            <h3>Opportunities</h3>
            <div class="value">{{ opportunities }}</div>
        </div>
        <div class="stat-card">
            <h3>Pipelines</h3>
            <div class="value">{{ pipelines }}</div>
        </div>
        <div class="stat-card">
            <h3>Users</h3>
            <div class="value">{{ users }}</div>
        </div>
    </div>
    <div class="stat-card">
        <h3>Last Updated</h3>
        <div>{{ last_update }}</div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    stats = {
        'contacts': '—',
        'opportunities': '—',
        'pipelines': '—',
        'users': '—',
        'last_update': 'Loading...'
    }
    
    if db:
        try:
            stats['contacts'] = db.collection('ghl_contacts').count().get()[0].value
        except: pass
        try:
            stats['opportunities'] = db.collection('ghl_opportunities').count().get()[0].value
        except: pass
        try:
            stats['pipelines'] = db.collection('ghl_pipelines').count().get()[0].value
        except: pass
        try:
            stats['users'] = db.collection('ghl_users').count().get()[0].value
        except: pass
    
    from datetime import datetime
    stats['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template_string(DASHBOARD_HTML, **stats)

@app.route('/api/stats')
def api_stats():
    stats = {}
    if db:
        try:
            stats['contacts'] = db.collection('ghl_contacts').count().get()[0].value
        except: stats['contacts'] = 0
        try:
            stats['opportunities'] = db.collection('ghl_opportunities').count().get()[0].value
        except: stats['opportunities'] = 0
        try:
            stats['pipelines'] = db.collection('ghl_pipelines').count().get()[0].value
        except: stats['pipelines'] = 0
        try:
            stats['users'] = db.collection('ghl_users').count().get()[0].value
        except: stats['users'] = 0
    return jsonify(stats)

# Vercel handler
def handler(request):
    return app(request.environ, lambda status, headers: request.respond(status, headers))
