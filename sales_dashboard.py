"""
Happy Solar Sales Dashboard - Opportunities Focus
Plotly Dash - Connects to Firestore
"""
import json
import os
from dash import Dash, html, dcc, callback, Output, Input
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from google.cloud import firestore

SERVICE_ACCOUNT_PATH = os.path.join(os.path.dirname(__file__), 'firebase-key.json')

# Initialize Firebase
try:
    db = firestore.Client.from_service_account_json(SERVICE_ACCOUNT_PATH, database='happy-solar')
    print("Firebase connected to happy-solar")
except Exception as e:
    print(f"Firebase error: {e}")
    db = None


def fetch_contacts():
    """Fetch all contacts from Firestore"""
    if not db:
        return pd.DataFrame()
    
    try:
        docs = db.collection('ghl_contacts').stream()
        contacts = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            contacts.append(data)
        
        df = pd.DataFrame(contacts)
        print(f"Loaded {len(df)} contacts from Firestore")
        return df
    except Exception as e:
        print(f"Error fetching contacts: {e}")
        return pd.DataFrame()


# Create Dash app
app = Dash(__name__)

# Fetch data
print("Loading data...")
try:
    df = fetch_contacts()
except:
    df = pd.DataFrame()

if df.empty:
    df = pd.DataFrame(columns=['id', 'firstName', 'lastName', 'phone', 'email', 'team', 'rep', 
                               'leadSource', 'type', 'syncedAt', 'setter', 'tags'])


# Layout
app.layout = html.Div([
    html.H1("Happy Solar - Opportunities Dashboard", 
            style={'textAlign': 'center', 'color': '#1a5276', 'marginBottom': '10px'}),
    
    html.P("Track opportunities, setters, lead sources, and team performance",
           style={'textAlign': 'center', 'color': '#7f8c8d', 'marginBottom': '30px'}),
    
    # Key Metrics Row
    html.Div([
        html.Div([
            html.H3("Total Opportunities", style={'margin': '0', 'color': '#7f8c8d'}),
            html.H2(f"{len(df):,}", style={'margin': '0', 'color': '#2980b9'})
        ], className="kpi-card"),
        
        html.Div([
            html.H3("With Setter", style={'margin': '0', 'color': '#7f8c8d'}),
            html.H2(f"{df['setter'].notna().sum():,}", style={'margin': '0', 'color': '#27ae60'})
        ], className="kpi-card"),
        
        html.Div([
            html.H3("Unique Setters", style={'margin': '0', 'color': '#7f8c8d'}),
            html.H2(f"{df['setter'].nunique():,}", style={'margin': '0', 'color': '#8e44ad'})
        ], className="kpi-card"),
        
        html.Div([
            html.H3("Teams Active", style={'margin': '0', 'color': '#7f8c8d'}),
            html.H2(f"{df['team'].nunique():,}", style={'margin': '0', 'color': '#e67e22'})
        ], className="kpi-card"),
    ], className="kpi-row"),
    
    # Charts Row 1: Opportunities by Setter & Team
    html.Div([
        html.Div([
            dcc.Graph(id='setter-chart')
        ], className="chart-card"),
        
        html.Div([
            dcc.Graph(id='team-chart')
        ], className="chart-card"),
    ], className="chart-row"),
    
    # Charts Row 2: Lead Sources & Pipeline Stage
    html.Div([
        html.Div([
            dcc.Graph(id='source-chart')
        ], className="chart-card"),
        
        html.Div([
            dcc.Graph(id='pipeline-chart')
        ], className="chart-card"),
    ], className="chart-row"),
    
    # Charts Row 3: Rep Performance & Conversion
    html.Div([
        html.Div([
            dcc.Graph(id='rep-chart')
        ], className="chart-card"),
        
        html.Div([
            dcc.Graph(id='conversion-chart')
        ], className="chart-card"),
    ], className="chart-row"),
    
    # Data Table
    html.Div([
        html.H3("Top Opportunities", style={'color': '#1a5276'}),
        html.Div(id='contacts-table')
    ], className="table-card"),
    
    # Refresh button
    html.Div([
        html.Button('Refresh Data', id='refresh-btn', n_clicks=0,
                   style={'padding': '12px 24px', 'fontSize': '14px', 
                          'backgroundColor': '#2980b9', 'color': 'white',
                          'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer',
                          'marginTop': '20px'})
    ], style={'textAlign': 'center', 'marginTop': '20px'}),
    
], style={'padding': '20px', 'fontFamily': 'Arial, sans-serif',
          'backgroundColor': '#f4f6f7', 'minHeight': '100vh'})


# Callbacks
@callback(
    [Output('setter-chart', 'figure'),
     Output('team-chart', 'figure'),
     Output('source-chart', 'figure'),
     Output('pipeline-chart', 'figure'),
     Output('rep-chart', 'figure'),
     Output('conversion-chart', 'figure'),
     Output('contacts-table', 'children')],
    [Input('refresh-btn', 'n_clicks')]
)
def update_dashboard(n_clicks):
    global df
    
    # Re-fetch on refresh
    if n_clicks > 0:
        df = fetch_contacts()
    
    # 1. Opportunities by Setter (top 15)
    setter_counts = df['setter'].value_counts().head(15).reset_index()
    setter_counts.columns = ['Setter', 'Opportunities']
    fig_setter = px.bar(setter_counts, x='Setter', y='Opportunities',
                       title='Opportunities by Setter',
                       color='Opportunities', color_continuous_scale='Greens')
    fig_setter.update_layout(paper_bgcolor='white', plot_bgcolor='white',
                           xaxis_tickangle=-45)
    
    # 2. Opportunities by Team
    team_counts = df['team'].value_counts().reset_index()
    team_counts.columns = ['Team', 'Opportunities']
    fig_team = px.bar(team_counts, x='Team', y='Opportunities',
                     title='Opportunities by Team',
                     color='Opportunities', color_continuous_scale='Blues')
    fig_team.update_layout(paper_bgcolor='white', plot_bgcolor='white')
    
    # 3. Lead Sources
    source_counts = df['leadSource'].value_counts().reset_index()
    source_counts.columns = ['Lead Source', 'Opportunities']
    fig_source = px.pie(source_counts, values='Opportunities', names='Lead Source',
                      title='Lead Sources Distribution')
    fig_source.update_traces(textposition='inside', textinfo='percent+label')
    fig_source.update_layout(paper_bgcolor='white')
    
    # 4. Pipeline Stage (from tags)
    # Extract pipeline stage from tags
    all_tags = []
    for tags in df['tags'].dropna():
        all_tags.extend(tags)
    
    tag_series = pd.Series(all_tags)
    tag_counts = tag_series.value_counts().head(12).reset_index()
    tag_counts.columns = ['Stage', 'Count']
    
    fig_pipeline = px.funnel(tag_counts, x='Count', y='Stage',
                           title='Pipeline Funnel (by Tag)')
    fig_pipeline.update_layout(paper_bgcolor='white', plot_bgcolor='white')
    
    # 5. Rep Performance (top 15)
    rep_counts = df['rep'].value_counts().head(15).reset_index()
    rep_counts.columns = ['Rep', 'Opportunities']
    fig_rep = px.bar(rep_counts, x='Rep', y='Opportunities',
                    title='Top Reps by Opportunities',
                    color='Opportunities', color_continuous_scale='Oranges')
    fig_rep.update_layout(paper_bgcolor='white', plot_bgcolor='white',
                         xaxis_tickangle=-45)
    
    # 6. Lead Source by Team (stacked bar)
    if not df['team'].empty and not df['leadSource'].empty:
        source_team = df.groupby(['leadSource', 'team']).size().reset_index(name='Count')
        fig_conversion = px.bar(source_team, x='leadSource', y='Count', color='team',
                              title='Lead Sources by Team',
                              barmode='group')
        fig_conversion.update_layout(paper_bgcolor='white', plot_bgcolor='white',
                                   xaxis_tickangle=-45)
    else:
        fig_conversion = go.Figure()
        fig_conversion.update_layout(title="Lead Sources by Team", paper_bgcolor='white')
    
    # 7. Sample table - show key opportunity fields
    sample = df[df['setter'].notna()][['firstName', 'lastName', 'phone', 'team', 'setter', 'leadSource']].head(25)
    
    table = html.Table([
        html.Tr([html.Th(col.title()) for col in sample.columns])
    ] + [
        html.Tr([html.Td(str(sample.iloc[i][col])) for col in sample.columns])
        for i in range(len(sample))
    ], style={'width': '100%', 'borderCollapse': 'collapse', 'fontSize': '13px'})
    
    return fig_setter, fig_team, fig_source, fig_pipeline, fig_rep, fig_conversion, table


# Add CSS
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Happy Solar - Opportunities Dashboard</title>
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
            table { borderCollapse: collapse; }
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
    print("Starting Happy Solar Dashboard...")
    print("Open http://localhost:8050 in your browser")
    # Use 0.0.0.0 for cloud deployment, port from env (Render)
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 8050))
    app.run(debug=False, host=host, port=port)

# Expose server for gunicorn
server = app.server
