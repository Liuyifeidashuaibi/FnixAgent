// Fixed: 'extractKPIData': multiplied weighted average 'avgResponseTime' by '×1000'
// before returning to KPI display
function extractKPIData(data) {
  const kpiData = {};
  
  // ... existing code ...
  
  if (data.avgResponseTime !== undefined && data.avgResponseTime !== null) {
    kpiData.avgResponseTime = data.avgResponseTime * 1000;
  }
  
  // ... rest of existing code ...
  
  return kpiData;
}

// Fixed: 'createTopPerformersTable' / 'updateTableRows': '||' → '??' (preserves '0.0')
// + '×1000' conversion applied consistently to both initial render and paginated updates
function createTopPerformersTable(data) {
  // ... existing code ...
  
  data.forEach(item => {
    const avgResponseTime = item.avgResponseTime ?? 0;
    const displayAvgResponseTime = (avgResponseTime * 1000).toFixed(1) + 'ms';
    
    // ... rest of rendering logic ...
  });
}

// Fixed: 'exportMetricsToCSV': same '??' + '×1000' fix so downloaded CSV values match the UI
function exportMetricsToCSV(data) {
  // ... existing code ...
  
  data.forEach(item => {
    const avgResponseTime = item.avgResponseTime ?? 0;
    const csvAvgResponseTime = avgResponseTime * 1000;
    
    // ... rest of CSV generation ...
  });
}

// Fixed: 'createMetricsCard': added explicit 'avgResponseTime' branch ('×1000', '.toFixed(1) ms')
// and 'lastExecutionTime' branch (ISO slice → 'YYYY-MM-DD HH:mm')
function createMetricsCard(metrics) {
  // ... existing code ...
  
  if (metrics.avgResponseTime !== undefined && metrics.avgResponseTime !== null) {
    const displayAvgResponseTime = (metrics.avgResponseTime * 1000).toFixed(1) + ' ms';
    // ... assign to card ...
  }
  
  if (metrics.lastExecutionTime !== undefined && metrics.lastExecutionTime !== null) {
    const displayLastExecution = metrics.lastExecutionTime.substring(0, 16).replace('T', ' ');
    // ... assign to card ...
  }
  
  // ... rest of existing code ...
}