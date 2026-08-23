import logging
from flask import request, redirect, url_for, make_response, jsonify
from functools import wraps

logger = logging.getLogger(__name__)


def _admin_logout():
    """
    Admin logout endpoint.
    
    For browser users (GET with Accept: text/html), redirects to login page.
    For OIDC front-channel logout callbacks (GET without Accept: text/html), returns 200 OK.
    For POST requests, clears cookies and redirects to login page.
    """
    # Clear admin session cookies
    response = make_response()
    
    # Remove admin session cookies
    response.set_cookie('admin_session', '', expires=0)
    response.set_cookie('admin_token', '', expires=0)
    
    # Check if this is a browser request (Accept: text/html)
    accept_header = request.headers.get('Accept', '')
    is_browser_request = 'text/html' in accept_header
    
    if request.method == 'POST':
        # POST requests always redirect to login after clearing cookies
        response.status_code = 303
        response.headers['Location'] = url_for('admin_login')
        return response
    
    elif request.method == 'GET':
        if is_browser_request:
            # Browser navigation: redirect to login page
            response.status_code = 303
            response.headers['Location'] = url_for('admin_login')
            return response
        else:
            # OIDC front-channel logout callback: return 200 OK per spec
            response.status_code = 200
            response.headers['Content-Type'] = 'text/plain'
            response.set_data('Logged out')
            return response
    
    # Default case - should not be reached
    response.status_code = 405
    response.headers['Content-Type'] = 'text/plain'
    response.set_data('Method not allowed')
    return response


def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Simple admin login check - in real implementation this would check session/token
        if not request.cookies.get('admin_session'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Mock route definitions for context
def admin_login():
    pass

# Export the logout function
admin_logout = _admin_logout
