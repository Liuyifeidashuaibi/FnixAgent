class MetricsCache:
    def __init__(self):
        self._cache = {}
    
    def get(self):
        return self._cache
    
    def set(self, value):
        self._cache = value

# Singleton instance
metrics_cache = MetricsCache()
