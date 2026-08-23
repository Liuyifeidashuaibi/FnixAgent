import datetime
import pytz
from sqlalchemy import func, case, and_, or_
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

def _compute_metrics_summary(db_session, model_class, model_id, start_time=None, end_time=None):
    """
    Compute metrics summary from both raw and hourly metrics tables.
    
    Uses time-based partitioning:
    - Current hour: query raw metrics table only
    - Completed hours: query hourly metrics table only
    - Prevents double-counting
    - Handles timezone normalization
    
    Args:
        db_session: SQLAlchemy session
        model_class: The model class (Tool, Resource, Prompt, Server)
        model_id: The ID of the specific model instance
        start_time: Optional start time for filtering
        end_time: Optional end time for filtering
    
    Returns:
        dict: Metrics summary with keys:
            - total_executions
            - successful_executions
            - failed_executions
            - failure_rate
            - avg_response_time
            - last_execution_time
    """
    # Get current time in UTC
    now = datetime.datetime.now(pytz.UTC)
    
    # Determine current hour boundary
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    
    # Build base query conditions
    base_conditions = [model_class.id == model_id]
    
    if start_time:
        base_conditions.append(model_class.created_at >= start_time)
    if end_time:
        base_conditions.append(model_class.created_at <= end_time)
    
    # Query raw metrics for current hour only
    raw_metrics_query = None
    if hasattr(model_class, 'raw_metrics'):
        raw_metrics_query = db_session.query(
            func.count().label('raw_count'),
            func.sum(case([(model_class.raw_metrics.status == 'success', 1)], else_=0)).label('raw_success'),
            func.sum(case([(model_class.raw_metrics.status == 'failure', 1)], else_=0)).label('raw_failure'),
            func.avg(model_class.raw_metrics.response_time).label('raw_avg_response_time'),
            func.max(model_class.raw_metrics.created_at).label('raw_last_execution')
        ).join(model_class.raw_metrics)
        
        # Filter for current hour only
        raw_metrics_query = raw_metrics_query.filter(
            model_class.raw_metrics.created_at >= current_hour_start
        )
        
        # Apply base conditions
        for condition in base_conditions:
            raw_metrics_query = raw_metrics_query.filter(condition)
    
    # Query hourly metrics for completed hours only
    hourly_metrics_query = None
    if hasattr(model_class, 'metrics_hourly'):
        hourly_metrics_query = db_session.query(
            func.sum(model_class.metrics_hourly.total_executions).label('hourly_total'),
            func.sum(model_class.metrics_hourly.successful_executions).label('hourly_success'),
            func.sum(model_class.metrics_hourly.failed_executions).label('hourly_failure'),
            func.avg(model_class.metrics_hourly.avg_response_time).label('hourly_avg_response_time'),
            func.max(model_class.metrics_hourly.hour_end).label('hourly_last_execution')
        ).join(model_class.metrics_hourly)
        
        # Filter for completed hours only (before current hour)
        hourly_metrics_query = hourly_metrics_query.filter(
            model_class.metrics_hourly.hour_end < current_hour_start
        )
        
        # Apply base conditions
        for condition in base_conditions:
            hourly_metrics_query = hourly_metrics_query.filter(condition)
    
    # Execute queries
    raw_result = None
    hourly_result = None
    
    if raw_metrics_query:
        raw_result = raw_metrics_query.first()
    
    if hourly_metrics_query:
        hourly_result = hourly_metrics_query.first()
    
    # Combine results
    total_executions = 0
    successful_executions = 0
    failed_executions = 0
    avg_response_time = 0.0
    last_execution_time = None
    
    # Process raw metrics
    if raw_result and raw_result.raw_count:
        total_executions += raw_result.raw_count
        successful_executions += raw_result.raw_success or 0
        failed_executions += raw_result.raw_failure or 0
        if raw_result.raw_avg_response_time:
            avg_response_time += raw_result.raw_avg_response_time
        last_execution_time = raw_result.raw_last_execution
    
    # Process hourly metrics
    if hourly_result and hourly_result.hourly_total:
        total_executions += hourly_result.hourly_total
        successful_executions += hourly_result.hourly_success or 0
        failed_executions += hourly_result.hourly_failure or 0
        if hourly_result.hourly_avg_response_time:
            avg_response_time += hourly_result.hourly_avg_response_time
        if hourly_result.hourly_last_execution:
            if not last_execution_time or hourly_result.hourly_last_execution > last_execution_time:
                last_execution_time = hourly_result.hourly_last_execution
    
    # Calculate averages
    if total_executions > 0:
        failure_rate = failed_executions / total_executions
        # If we have both raw and hourly response times, calculate weighted average
        if raw_result and raw_result.raw_avg_response_time and hourly_result and hourly_result.hourly_avg_response_time:
            # Simple average for now
            avg_response_time = (raw_result.raw_avg_response_time + hourly_result.hourly_avg_response_time) / 2
        elif raw_result and raw_result.raw_avg_response_time:
            avg_response_time = raw_result.raw_avg_response_time
        elif hourly_result and hourly_result.hourly_avg_response_time:
            avg_response_time = hourly_result.hourly_avg_response_time
    else:
        failure_rate = 0.0
        avg_response_time = 0.0
    
    return {
        'total_executions': total_executions,
        'successful_executions': successful_executions,
        'failed_executions': failed_executions,
        'failure_rate': round(failure_rate, 3) if total_executions > 0 else 0.0,
        'avg_response_time': round(avg_response_time, 2) if avg_response_time else 0.0,
        'last_execution_time': last_execution_time.isoformat() if last_execution_time else None
    }
