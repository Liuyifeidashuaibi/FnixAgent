import os
from flask import render_template, request, redirect, url_for

# Get MAX_MEMBERS_PER_TEAM from environment, default to 100
MAX_MEMBERS_PER_TEAM = int(os.environ.get('MAX_MEMBERS_PER_TEAM', '100'))

# Mock function to render the admin page with context
def render_admin_page():
    # Pass the setting to the template context
    return render_template('admin.html', 
                          max_members_per_team=MAX_MEMBERS_PER_TEAM,
                          is_admin=True)  # In real app, this would be determined by user role

# Mock function for edit team form rendering
def render_edit_team_form(team_id):
    # In real app, this would fetch team data
    team = {'id': team_id, 'name': 'Sample Team', 'max_members': 50}
    
    # Render the edit form with proper max attribute based on user role
    # For non-admin users, we'd set max to MAX_MEMBERS_PER_TEAM
    # For admin users, no max attribute
    return render_template('admin.html', 
                          max_members_per_team=MAX_MEMBERS_PER_TEAM,
                          is_admin=True,  # In real app, this would be determined by user role
                          team=team)

# Mock route handlers
@route('/admin')
def admin_page():
    return render_admin_page()

@route('/admin/team/edit/<int:team_id>')
def edit_team(team_id):
    return render_edit_team_form(team_id)
