from django.contrib import admin
from django.urls import path
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

# Mock implementation of the admin functionality with split search

def get_team_members(request):
    """
    Get team members with optional search parameter
    """
    # Extract search parameter from request
    search_term = request.GET.get('search', '').strip()
    
    # Simulate server-side filtering
    if search_term:
        # In real implementation, this would query the database with LIKE clause
        # and use _escape_like() for SQL injection prevention
        pass
    
    # Return mock data
    return JsonResponse({
        'members': [],
        'non_members': []
    })

@csrf_exempt
def serverSideMemberSearch(request):
    """
    Server-side search for current members only
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        search_term = data.get('search', '').strip()
        
        # Server-side filtering logic for members only
        # Results capped at 50 as per PR requirements
        return JsonResponse({
            'results': [],
            'count': 0
        })
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def serverSideNonMemberSearch(request):
    """
    Server-side search for non-members only
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        search_term = data.get('search', '').strip()
        
        # Server-side filtering logic for non-members only
        # Results capped at 50 as per PR requirements
        # Minimum 2-char enforced
        if len(search_term) < 2:
            return JsonResponse({
                'results': [],
                'count': 0,
                'error': 'Search term must be at least 2 characters'
            })
        
        return JsonResponse({
            'results': [],
            'count': 0
        })
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

# URL patterns
urlpatterns = [
    path('api/team-members/', get_team_members, name='get_team_members'),
    path('api/server-side-member-search/', serverSideMemberSearch, name='serverSideMemberSearch'),
    path('api/server-side-non-member-search/', serverSideNonMemberSearch, name='serverSideNonMemberSearch'),
]