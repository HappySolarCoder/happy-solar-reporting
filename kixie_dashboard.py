"""
Happy Solar - Kixie Call Center Dashboard
Shows calls per agent with connections and connection rate
"""
import os
from dash import Dash, html, dcc, callback, Output, Input
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from google.cloud import firestore
from datetime import datetime, timedelta

SERVICE_ACCOUNT_PATH = os.path.join(os.path.dirname(__file__), 'firebase-key.json')

# Initialize Firebase
try:
    db = firestore.Client.from_service_account_json(SERVICE_ACCOUNT_PATH, database='happy-solar')
    print("Firebase connected")
except Exception as e:
    print(f"Firebase error: {e}")
    db = None


def fetch_calls():
    """Fetch all Kixie calls from Firestore"""
    if not db:
        return pd.DataFrame()
    
    try:
        docs = db.collection('kixie_calls').stream()
        calls = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            calls.append(data)
        
        df = pd.DataFrame(calls)
        print(f"Loaded {len(df)} calls from Firestore")
        return df
    except Exception as e:
        print(f"Error fetching calls: {e}")
        return pd.DataFrame()


# Create Dash app
app = Dash(__name__)

# Fetch data
print("Loading call data...")
df = fetch_calls()

if df.empty:
    df = pd.DataFrame(columns=['id', 'agent', 'phoneNumber', 'direction', 'outcome', 
                               'duration', 'callDate', 'callEndDate', 'receivedAt'])

# Process dates
if 'callDate' in df.columns and not df.empty:
    df['callDate'] = pd.to_datetime(df['callDate'], errors='coerce')
    df['date'] = df['callDate'].dt.date
elif not df.empty:
    df['date'] = None

# Get date range for filter
if not df.empty and 'date' in df.columns:
    dates = df['date'].dropna().sort_values()
    if len(dates) > 0:
        min_date = dates.min()
        max_date = dates.max()
    else:
        min_date = max_date = datetime.now().date()
else:
    min_date = max_date = datetime.now().date()


# Layout
app.layout = html.Div([
    html.H1("Kixie Call Center Dashboard", 
            style={'textAlign': 'center', 'color': '#1a5276', 'marginBottom': '10px'}),
    
    html.P("Track call volume, connections, and agent performance",
           style={'textAlign': 'center', 'color': '#7f8c8d', 'marginBottom': '20px'}),
    
    # Date Filter
    html.Div([
        html.Label("Date Range:", style={'fontWeight': 'bold', 'marginRight': '10px'}),
        dcc.DatePickerRange(
            id='date-picker',
            start_date=min_date,
            end_date=max_date,
            display_format='YYYY-MM-DD'
        ),
        html.Button('Apply Filter', id='apply-filter', n_clicks=0,
                   style={'marginLeft': '10px', 'padding': '8px 16px', 
                          'backgroundColor': '#2980b9', 'color': 'white',
                          'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer'})
    ], style={'textAlign': 'center', 'marginBottom': '30px', 'padding': '20px',
              'backgroundColor': 'white', 'borderRadius': '10px', 'boxShadow': '0 2px 10px rgba(0,0,0,0.1)'}),
    
    # KPI Cards
    html.Div([
        html.Div([
            html.H3("Total Calls", style={'margin': '0', 'color': '#7f8c8d'}),
            html.H2(id='total-calls', style={'margin': '0', 'color': '#2980b9'})
        ], className="kpi-card"),
        
        html.Div([
            html.H3("Connections", style={'margin': '0', 'color': '#7f8c8d'}),
            html.H2(id='total-connections', style={'margin': '0', 'color': '#27ae60'})
        ], className="kpi-card"),
        
        html.Div([
            html.H3("Connection Rate", style={'margin': '0', 'color': '#7f8c8d'}),
            html.H2(id='connection-rate', style={'margin': '0', 'color': '#8e44ad'})
        ], className="kpi-card"),
        
        html.Div([
            html.H3("Total Talk Time", style={'margin': '0', 'color': '#7f8c8d'}),
            html.H2(id='total-talk-time', style={'margin': '0', 'color': '#e67e22'})
        ], className="kpi-card"),
    ], className="kpi-row"),
    
    # Charts
    html.Div([
        html.Div([
            dcc.Graph(id='outcome-chart')
        ], className="chart-card"),
        
        html.Div([
            dcc.Graph(id='agent-chart')
        ], className="chart-card"),
    ], className="chart-row"),
    
    # Agent Table
    html.Div([
        html.H3("Agent Performance", style={'color': '#1a5276', 'marginBottom': '15px'}),
        html.Div(id='agent-table')
    ], className="table-card"),
    
    # Refresh
    html.Div([
        html.Button('Refresh Data', id='refresh-btn', n_clicks=0,
                   style={'padding': '10px 20px', 'fontSize': '14px', 
                          'backgroundColor': '#2980b9', 'color': 'white',
                          'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer',
                          'marginTop': '20px'}),
        dcc.Interval(id='auto-refresh', interval=30*1000, n_intervals=0)  # Auto-refresh every 30 seconds
    ], style={'textAlign': 'center', 'marginTop': '20px'}),
    
], style={'padding': '20px', 'fontFamily': 'Arial, sans-serif',
          'backgroundColor': '#f4f6f7', 'minHeight': '100vh'})


@callback(
    [Output('total-calls', 'children'),
     Output('total-connections', 'children'),
     Output('connection-rate', 'children'),
     Output('total-talk-time', 'children'),
     Output('outcome-chart', 'figure'),
     Output('agent-chart', 'figure'),
     Output('agent-table', 'children')],
    [Input('apply-filter', 'n_clicks'),
     Input('date-picker', 'start_date'),
     Input('date-picker', 'end_date'),
     Input('refresh-btn', 'n_clicks'),
     Input('auto-refresh', 'n_intervals')]
)
def update_dashboard(apply_clicks, start_date, end_date, refresh_clicks, auto_refresh):
    global df
    
    # Refresh data if button clicked OR on auto-refresh interval
    if refresh_clicks > 0 or auto_refresh > 0:
        df = fetch_calls()
        if 'callDate' in df.columns and not df.empty:
            df['callDate'] = pd.to_datetime(df['callDate'], errors='coerce')
            df['date'] = df['callDate'].dt.date
    
    if df.empty:
        return "0", "0", "0%", "0m", go.Figure(), go.Figure(), "No data"
    
    # Filter by date
    filtered_df = df.copy()
    if start_date and end_date:
        start = pd.to_datetime(start_date).date() if isinstance(start_date, str) else start_date
        end = pd.to_datetime(end_date).date() if isinstance(end_date, str) else end_date
        
        if 'date' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['date'].notna()]
            filtered_df = filtered_df[(filtered_df['date'] >= start) & (filtered_df['date'] <= end)]
    
    # Calculate KPIs
    total_calls = len(filtered_df)
    
    # Connection = calls with outcome 'connected' or 'answered'
    connected_outcomes = ['connected', 'answered', 'success']
    connections = filtered_df[filtered_df['outcome'].isin(connected_outcomes)].shape[0]
    
    connection_rate = f"{(connections/total_calls*100):.1f}%" if total_calls > 0 else "0%"
    
    # Total talk time in minutes
    total_duration = filtered_df['duration'].sum() if 'duration' in filtered_df.columns else 0
    talk_minutes = int(total_duration / 60)
    if talk_minutes > 60:
        talk_time = f"{talk_minutes//60}h {talk_minutes%60}m"
    else:
        talk_time = f"{talk_minutes}m"
    
    # Outcome chart
    outcome_counts = filtered_df['outcome'].value_counts().reset_index()
    outcome_counts.columns = ['Outcome', 'Count']
    fig_outcome = px.pie(outcome_counts, values='Count', names='Outcome',
                        title='Call Outcomes')
    fig_outcome.update_traces(textposition='inside', textinfo='percent+label')
    fig_outcome.update_layout(paper_bgcolor='white')
    
    # Agent chart - calls per agent
    agent_counts = filtered_df['agent'].value_counts().head(10).reset_index()
    agent_counts.columns = ['Agent', 'Calls']
    fig_agent = px.bar(agent_counts, x='Agent', y='Calls',
                     title='Calls by Agent',
                     color='Calls', color_continuous_scale='Blues')
    fig_agent.update_layout(paper_bgcolor='white', plot_bgcolor='white',
                         xaxis_tickangle=-45)
    
    # Agent table with connections and rate
    agent_stats = filtered_df.groupby('agent').agg({
        'id': 'count',
        'outcome': lambda x: sum(x.isin(connected_outcomes)),
        'duration': 'sum'
    }).reset_index()
    agent_stats.columns = ['Agent', 'Total Calls', 'Connections', 'Total Duration']
    
    # Calculate connection rate per agent
    agent_stats['Connection %'] = agent_stats.apply(
        lambda r: f"{(r['Connections']/r['Total Calls']*100):.1f}%" if r['Total Calls'] > 0 else "0%",
        axis=1
    )
    agent_stats['Talk Time'] = agent_stats['Total Duration'].apply(
        lambda x: f"{int(x/60)}m" if x < 3600 else f"{x//60}h {x%60}m"
    )
    
    # Sort by connections
    agent_stats = agent_stats.sort_values('Connections', ascending=False)
    
    # Create table
    table = html.Table([
        html.Tr([
            html.Th('Agent'),
            html.Th('Total Calls'),
            html.Th('Connections'),
            html.Th('Connection %'),
            html.Th('Talk Time')
        ])
    ] + [
        html.Tr([
            html.Td(row['Agent']),
            html.Td(row['Total Calls']),
            html.Td(row['Connections']),
            html.Td(row['Connection %']),
            html.Td(row['Talk Time'])
        ])
        for _, row in agent_stats.iterrows()
    ], style={'width': '100%', 'borderCollapse': 'collapse'})
    
    return (
        str(total_calls),
        str(connections),
        connection_rate,
        talk_time,
        fig_outcome,
        fig_agent,
        table
    )


# CSS
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Kixie Call Center Dashboard</title>
        {%favicon%}
        {%css%}
        <style>
            .kpi-row { display: flex; justify-content: space-around; marginBottom: 30px; flex-wrap: wrap; gap: 15px; }
            .kpi-card { 
                background: white; padding: 20px 30px; borderRadius: 10px; 
                boxShadow: 0 2px 10px rgba(0,0,0,0.1); textAlign: center; minWidth: 140px;
            }
            .chart-row { display: flex; justify-content: space-between; marginBottom: 20px; flex-wrap: wrap; }
            .chart-card { flex: 1; minWidth: 400px; margin: 0 10px; background: white; padding: 15px; borderRadius: 10px; boxShadow: 0 2px 10px rgba(0,0,0,0.1); }
            .table-card { background: white; padding: 20px; borderRadius: 10px; boxShadow: 0 2px 10px rgba(0,0,0,0.1); marginTop: 20px; }
            table { borderCollapse: collapse; width: 100%; }
            th { background: #2980b9; color: white; padding: 12px; textAlign: left; }
            td { padding: 10px; borderBottom: 1px solid #ecf0f1; }
            tr:hover { background: #f8f9fa; }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

if __name__ == '__main__':
    print("Starting Kixie Dashboard...")
    print("Open http://localhost:8051 in your browser")
    app.run(debug=True, port=8051)
