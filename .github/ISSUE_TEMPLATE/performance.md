---
name: Performance issue
about: Report a performance regression, slow operation, or high resource usage
title: '[Perf] '
labels: performance
---

## Summary

<!-- One-sentence description of the performance problem. -->



## Environment

- OS: <!-- e.g., Windows 11 23H2, macOS 14.5, Ubuntu 24.04 -->
- CPU: <!-- e.g., Apple M2, Intel i7-13700H -->
- RAM: <!-- e.g., 16 GB -->
- FnixAgent version: <!-- e.g., v1.0.0-beta.1 -->
- Workload: <!-- e.g., "agentd + Work mode, 10 concurrent sessions, qwen-long context" -->

## Measurement

### Current (problematic) performance

| Metric | Value |
|--------|-------|
| Wall-clock time | <!-- e.g., 12.4s --> |
| CPU usage | <!-- e.g., 95% (single core) --> |
| Memory (RSS) | <!-- e.g., 1.8 GB --> |
| Disk I/O | <!-- if relevant --> |
| Network | <!-- if relevant --> |

### Expected performance

| Metric | Value |
|--------|-------|
| Wall-clock time | <!-- e.g., < 2s --> |
| CPU usage | <!-- e.g., < 60% --> |
| Memory (RSS) | <!-- e.g., < 500 MB --> |

## Reproduction Steps

1. 
2. 
3. 

## Profiling Data

<!-- Attach flamegraphs, py-spy / scalene / cProfile output, browser DevTools traces, etc. -->

```
Paste profile output here
```

## Suggested Mitigation (optional)

<!-- If you have a hunch about the root cause or a fix, share it. -->

## Related

- Benchmarks: <!-- e.g., benchmarks/code/curated/manifest.json -->
- Profiling run: <!-- e.g., ./scripts/bench.py or link to artifacts -->
