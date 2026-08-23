from django.contrib import admin
from .models import Team, Member

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'members__name', 'members__email')

    def get_search_results(self, request, queryset, search_term):
        # Implement custom search logic here
        pass

@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'email')
    search_fields = ('name', 'email')

    def get_search_results(self, request, queryset, search_term):
        # Implement custom search logic here
        pass