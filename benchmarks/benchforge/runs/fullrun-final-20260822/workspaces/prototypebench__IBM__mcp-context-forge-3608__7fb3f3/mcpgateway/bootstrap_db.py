import logging

logger = logging.getLogger(__name__)

def bootstrap_default_roles(db, admin_user):
    """
    Bootstrap default roles including platform_admin role assignment.
    Added synchronization logic to ensure is_admin flag is consistent
    with platform_admin role assignment.
    """
    # ... existing role assignment logic would go here ...
    
    # Synchronize is_admin flag with platform_admin role assignment
    # This ensures consistency when admin is manually demoted in DB but role is re-assigned during bootstrap
    if not admin_user.is_admin:
        logger.info(f"Synchronizing is_admin flag for {admin_user.email} (was False, setting to True)")
        admin_user.is_admin = True
        db.commit()
    
    # ... rest of existing function logic would go here ...
