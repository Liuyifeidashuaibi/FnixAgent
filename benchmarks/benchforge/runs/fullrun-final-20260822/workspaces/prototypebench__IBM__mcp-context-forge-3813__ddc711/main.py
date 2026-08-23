from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# Placeholder imports - in real implementation these would be actual imports
from observability_middleware import ObservabilityMiddleware


def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session for route handlers.
    
    Transaction Control Policy:
    - ALWAYS controls transactions (commit/rollback) regardless of whether
      the session is newly created or reused from middleware
    - Commits on successful completion of route handler
    - Rolls back on any exception from route handler
    - Invalidates broken connections on failure
    - Does NOT close the session (middleware owns lifecycle)
    
    This maintains predictable transaction semantics where route handlers
    can rely on automatic rollback when raising exceptions, preventing
    data integrity violations like invalid data being committed.
    
    NOTE: This separation of concerns is critical:
    - Middleware manages session LIFECYCLE (create/close)
    - get_db() manages TRANSACTIONS (commit/rollback)
    """
    # Get session from request state (created by ObservabilityMiddleware)
    # In real implementation, this would be: request.state.db
    db = _get_session_from_request()
    
    try:
        yield db
        
        # Commit on successful completion
        if db and hasattr(db, 'is_active') and db.is_active:
            try:
                db.commit()
            except SQLAlchemyError as e:
                # Log the commit error
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to commit transaction: {str(e)}"
                )
                
    except Exception as exc:
        # Rollback on any exception
        if db:
            try:
                db.rollback()
            except Exception:
                # Connection may be broken, try to invalidate
                try:
                    if hasattr(db, 'invalidate'):
                        db.invalidate()
                except Exception:
                    pass  # nosec B110
        raise
    
    # Don't close the session - middleware owns lifecycle management
    # The session will be closed in the middleware's finally block


def _get_session_from_request() -> Optional[Session]:
    # Placeholder for getting session from request state
    # In real implementation, this would access request.state.db
    pass

# Example route handler demonstrating the pattern
# @app.post("/items")
# async def create_item(item: Item, db: Session = Depends(get_db)):
#     db_item = DBItem(**item.dict())
#     db.add(db_item)
#     
#     if not validate(db_item):
#         raise ValueError("Invalid")  # This will trigger rollback
#     
#     # Valid items will be committed by get_db() on success
#     return db_item
