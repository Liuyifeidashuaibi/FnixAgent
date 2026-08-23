from flask import Flask, request, jsonify, render_template_string
import time
import json
from config import get_gateway_config, DEFAULT_GATEWAY_ID

app = Flask(__name__)

# Mock MCP server tools data
mock_tools = [
    {"id": "tool-001", "name": "File Reader", "description": "Reads files from the filesystem"},
    {"id": "tool-002", "name": "Web Scraper", "description": "Extracts data from web pages"},
    {"id": "tool-003", "name": "API Connector", "description": "Connects to external APIs"},
    {"id": "tool-004", "name": "Data Analyzer", "description": "Analyzes structured data"}
]

@app.route('/')
def index():
    gateway_config = get_gateway_config(DEFAULT_GATEWAY_ID)
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP Context Forge - Tool Refresh</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; margin: 2rem; }
        .refresh-btn {
            background-color: #007bff;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            margin: 0.5rem 0;
        }
        .refresh-btn:hover {
            background-color: #0056b3;
        }
        .refresh-btn:disabled {
            background-color: #6c757d;
            cursor: not-allowed;
        }
        .status {
            margin-top: 1rem;
            padding: 0.5rem;
            border-radius: 4px;
        }
        .success { background-color: #d4edda; color: #155724; }
        .error { background-color: #f8d7da; color: #721c24; }
        .loading { background-color: #fff3cd; color: #856404; }
        .tools-list { margin-top: 1rem; }
        .tool-item { margin: 0.5rem 0; padding: 0.5rem; border-left: 4px solid #007bff; }
    </style>
</head>
<body>
    <h1>MCP Context Forge</h1>
    
    <div id="gateway-section">
        <h2>Gateway Management</h2>
        <div class="gateway-item">
            <h3>Gateway ID: {{ gateway_config['gateway_id'] }}</h3>
            <button class="refresh-btn" 
                    hx-post="/gateway/{{ gateway_config['gateway_id'] }}/refresh/tools" 
                    hx-target="#tools-status" 
                    hx-swap="innerHTML"
                    hx-indicator="#refresh-indicator">
                Refresh Tools
            </button>
            <span id="refresh-indicator" class="loading" style="display:none;">Refreshing...</span>
            <div id="tools-status" class="status"></div>
        </div>
    </div>

    <div id="tools-section">
        <h2>Available Tools</h2>
        <div id="tools-list" class="tools-list">
            <p>Loading tools...</p>
        </div>
    </div>

    <script>
        // Auto-refresh tools list when page loads
        document.addEventListener('DOMContentLoaded', function() {
            htmx.ajax('GET', '/tools/list', {target: '#tools-list'});
        });
        
        // Handle HTMX response events
        document.body.addEventListener('htmx:afterOnLoad', function(evt) {
            if (evt.detail.elt.id === 'tools-status') {
                // Add auto-hide for status messages after 3 seconds
                setTimeout(() => {
                    if (evt.detail.elt.classList.contains('success') || 
                        evt.detail.elt.classList.contains('error')) {
                        evt.detail.elt.style.display = 'none';
                    }
                }, 3000);
            }
        });
    </script>
</body>
</html>
''', gateway_config=gateway_config)

@app.route('/tools/list')
def list_tools():
    # Simulate network delay
    time.sleep(0.5)
    
    tools_html = '''<div class="tools-list">'''
    
    for tool in mock_tools:
        tools_html += f'''
        <div class="tool-item">
            <strong>{tool['name']}</strong><br>
            <small>{tool['description']}</small>
        </div>
        '''
    
    tools_html += '''</div>'''
    
    return tools_html

@app.route('/gateway/<gateway_id>/refresh/tools', methods=['POST'])
def refresh_tools(gateway_id):
    # Simulate MCP server refresh operation
    time.sleep(1.0)
    
    # In a real implementation, this would call the MCP server's /tools/list endpoint
    # and update the gateway's tool cache
    
    response_html = '''<div class="status success">✅ Tools refreshed successfully! Updated at ''' + time.strftime('%H:%M:%S') + '''</div>'''
    
    return response_html

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)