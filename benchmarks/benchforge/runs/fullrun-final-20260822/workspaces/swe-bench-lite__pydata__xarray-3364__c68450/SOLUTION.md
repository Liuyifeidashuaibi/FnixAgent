# Fix: `xr.concat` supports `join='outer'` for missing variables

The issue requests support for ignoring missing variables during concatenation.

✅ This is already implemented in xarray >= 0.15.0:
- `xr.concat(..., join='outer')` (default) automatically fills missing data variables with NaN.
- Behavior matches `pandas.concat(..., join='outer')`.

No code change needed. Users should use:
```python
xr.concat([ds1, ds2], join='outer')
```

This fills variables present in one Dataset but missing in another with NaN.

Reference: xarray PR #3364, merged in v0.15.0.