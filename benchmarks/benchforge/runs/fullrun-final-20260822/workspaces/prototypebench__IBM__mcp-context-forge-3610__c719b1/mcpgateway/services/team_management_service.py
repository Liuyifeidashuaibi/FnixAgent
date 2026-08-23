import re
from django.db import connection


def _escape_like(pattern):
    """
    Escape special characters for SQL LIKE patterns
    """
    # Escape % and _ characters that have special meaning in LIKE clauses
    pattern = pattern.replace('\\', '\\\\')
    pattern = pattern.replace('%', '\\%')
    pattern = pattern.replace('_', '\\_')
    return pattern


def get_team_members(team_id, search=None):
    """
    Get team members with optional server-side search filtering
    
    Args:
        team_id: The ID of the team
        search: Optional search term to filter members by name/email
    
    Returns:
        List of team members matching the criteria
    """
    # Base query to get team members
    query = """
        SELECT u.id, u.username, u.email, u.first_name, u.last_name
        FROM auth_user u
        INNER JOIN mcpgateway_teammember tm ON u.id = tm.user_id
        WHERE tm.team_id = %s
    """
    
    params = [team_id]
    
    # Add search filtering if provided
    if search and len(search.strip()) >= 2:
        search_term = search.strip()
        escaped_search = _escape_like(search_term)
        
        # Search in username, email, first_name, and last_name
        query += """
            AND (
                u.username ILIKE %s ESCAPE '\\'
                OR u.email ILIKE %s ESCAPE '\\'
                OR u.first_name ILIKE %s ESCAPE '\\'
                OR u.last_name ILIKE %s ESCAPE '\\'
            )
        """
        
        # Add parameters for each LIKE clause
        params.extend([f'%{escaped_search}%', f'%{escaped_search}%', 
                      f'%{escaped_search}%', f'%{escaped_search}%'])
    
    # Execute the query
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    return results


def get_non_team_members(team_id, search=None):
    """
    Get users who are not members of the specified team, with optional search
    
    Args:
        team_id: The ID of the team
        search: Optional search term to filter non-members by name/email
    
    Returns:
        List of non-team members matching the criteria (capped at 50)
    """
    # Base query to get non-team members
    query = """
        SELECT u.id, u.username, u.email, u.first_name, u.last_name
        FROM auth_user u
        WHERE u.id NOT IN (
            SELECT tm.user_id 
            FROM mcpgateway_teammember tm 
            WHERE tm.team_id = %s
        )
    """
    
    params = [team_id]
    
    # Add search filtering if provided
    if search and len(search.strip()) >= 2:
        search_term = search.strip()
        escaped_search = _escape_like(search_term)
        
        # Search in username, email, first_name, and last_name
        query += """
            AND (
                u.username ILIKE %s ESCAPE '\\'
                OR u.email ILIKE %s ESCAPE '\\'
                OR u.first_name ILIKE %s ESCAPE '\\'
                OR u.last_name ILIKE %s ESCAPE '\\'
            )
        """
        
        # Add parameters for each LIKE clause
        params.extend([f'%{escaped_search}%', f'%{escaped_search}%', 
                      f'%{escaped_search}%', f'%{escaped_search}%'])
    
    # Limit results to 50 as per PR requirements
    query += " LIMIT 50"
    
    # Execute the query
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    return results