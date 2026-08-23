from flask import Flask, Blueprint

# Configure server name
app = Flask(__name__)
app.config['SERVER_NAME'] = 'test.local'

# Blueprint: admin.test.local
admin_bp = Blueprint('admin_blueprint', __name__)
@admin_bp.route('/home')
def admin_home():
    return 'Admin home'

# Blueprint: test.test.local
test_bp = Blueprint('test_subdomain_blueprint', __name__)
@test_bp.route('/home')
def test_home():
    return 'Test subdomain home'

# Register with subdomains
app.register_blueprint(admin_bp, url_prefix='', subdomain='admin')
app.register_blueprint(test_bp, url_prefix='', subdomain='test')

# Default domain: test.local
@app.route('/ping')
def ping():
    return 'OK'

# --- Custom CLI command ---
import click
from flask.cli import with_appcontext

@app.cli.command()
@with_appcontext
def routes_with_domain():
    """Show all routes with their effective domain."""
    server_name = app.config.get('SERVER_NAME')
    if not server_name:
        click.echo('Warning: SERVER_NAME is not set. Cannot resolve domains.', err=True)
        return

    # Header
    click.echo(f"{'Domain':<20} {'Endpoint':<40} {'Methods':<10} {'Rule'}")
    click.echo(f"{'-'*19} {'-'*39} {'-'*9} {'-'*30}")

    rules = list(app.url_map.iter_rules())
    rules.sort(key=lambda r: (r.subdomain or '', r.rule))

    for rule in rules:
        # Compute domain
        if rule.subdomain is None:
            domain = server_name
        else:
            # e.g., subdomain='admin' + server_name='test.local' => 'admin.test.local'
            domain = f'{rule.subdomain}.{server_name}'

        methods = ','.join(sorted(rule.methods)) if rule.methods else 'ANY'
        endpoint = rule.endpoint
        rule_str = str(rule)

        click.echo(f"{domain:<20} {endpoint:<40} {methods:<10} {rule_str}")
