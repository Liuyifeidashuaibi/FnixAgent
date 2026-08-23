def get_team_members(team_id, search=None):
    from .models import Member
    query = Member.objects.filter(teams=team_id)
    if search:
        search = _escape_like(search)
        query = query.filter(
            Q(name__icontains=search) | Q(email__icontains=search)
        )
    return query.all()

def _escape_like(value, wildcards='\%_'):
    for wildcard in wildcards:
        value = value.replace(wildcard, f'\\{wildcard}')
    return value