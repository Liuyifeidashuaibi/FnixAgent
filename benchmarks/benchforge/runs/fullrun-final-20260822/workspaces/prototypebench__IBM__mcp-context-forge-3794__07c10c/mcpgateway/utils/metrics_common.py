def build_top_performers():
    # ... existing code ...
    
    # Fixed: Changed falsy checks to explicit 'is not None' guards
    # so '0.0' values are preserved
    avg_response_time=float(result.avg_response_time) if result.avg_response_time is not None else None,
    success_rate=float(result.success_rate) if result.success_rate is not None else None,
    
    # ... rest of existing code ...