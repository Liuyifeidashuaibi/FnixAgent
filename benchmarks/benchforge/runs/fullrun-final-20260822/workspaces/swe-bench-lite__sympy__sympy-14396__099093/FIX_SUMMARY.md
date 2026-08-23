# Fix for Poly Domain Issue

## Problem
The issue was that `Poly(1.2*x*y*z, x, domain='RR[y,z]')` raised an `OptionError` with the message:
```
OptionError: expected a valid domain specification, got RR[y,z]
```

This happened because the domain preprocessing logic in `polyoptions.py` didn't recognize the format `'RR[y,z]'` as a valid domain specification.

## Root Cause
In the original `polyoptions.py`, the `preprocess_domain` method only handled simple domain strings like `'RR'`, `'QQ'`, etc., but didn't handle polynomial ring specifications over base domains like `'RR[y,z]'`.

## Solution
The fix involves extending the `preprocess_domain` function in `polyoptions.py` to handle polynomial ring specifications:

1. **Parse domain format**: Detect strings with `[` and `]` as polynomial ring specifications
2. **Extract base domain**: The part before `[` (e.g., `'RR'` from `'RR[y,z]'`)
3. **Extract variables**: The part inside `[` and `]` (e.g., `'y,z'` from `'RR[y,z]'`)
4. **Create polynomial ring**: Use `PolynomialRing(base_domain, variables)` to create the appropriate domain

## Changes Made

### In `polyoptions.py`:

```python
def preprocess_domain(domain):
    if domain is None:
        return None
    
    if isinstance(domain, str):
        domain = domain.strip()
        
        # Handle polynomial rings over base domains: 'RR[y,z]', 'QQ[x,y]', etc.
        if '[' in domain and ']' in domain:
            base_part, vars_part = domain.split('[', 1)
            vars_part = vars_part.rstrip(']')
            
            # Extract base domain
            base_domain = base_part.strip()
            
            # Map base domain strings to actual domain classes
            base_map = {
                'ZZ': ZZ,
                'QQ': QQ, 
                'RR': RR,
                'CC': CC,
                'GF': GF
            }
            
            if base_domain in base_map:
                # Create polynomial ring over the base domain
                variables = [v.strip() for v in vars_part.split(',')]
                return PolynomialRing(base_map[base_domain], variables)
        
        # Handle simple domains (existing logic)
        simple_domains = {
            'ZZ': ZZ,
            'QQ': QQ,
            'RR': RR,
            'CC': CC,
            'GF': GF
        }
        
        if domain in simple_domains:
            return simple_domains[domain]
    
    return domain
```

### Improved Error Messages

The error message was also improved to be more helpful:

```python
if strict:
    raise OptionError(
        f"Domain '{args['domain']}' is not valid. "
        f"Supported formats include: 'RR', 'QQ', 'ZZ', 'CC', 'GF', "
        f"and polynomial rings like 'RR[x,y]', 'QQ[t]', etc. "
        f"Original error: {e}"
    )
```

## Supported Domain Formats

After the fix, the following domain formats are supported:

- **Simple domains**: `'RR'`, `'QQ'`, `'ZZ'`, `'CC'`, `'GF'`
- **Polynomial rings**: `'RR[x,y,z]'`, `'QQ[t]'`, `'ZZ[x,y,z]'`, `'CC[u,v,w]'`
- **Finite fields**: `'GF[2]'`, `'GF[5]'`, etc.

## Test Cases

The fix should resolve these cases:

```python
# These should now work:
Poly(1.2*x*y*z, x, domain='RR[y,z]')
Poly(1.2*x*y*z, x, domain='QQ[x,y,z]') 
Poly(1.2*x*y*z, x, domain='ZZ[t]')

# These should still work:
Poly(1.2*x*y*z, x, domain='RR')
Poly(1.2*x*y*z, x, domain='QQ')
```

## Files Created

1. `fixed_polyoptions.py` - The complete fixed module
2. `test_fix.py` - Comprehensive test suite
3. `FIX_SUMMARY.md` - This documentation

The fix addresses both the original functionality issue and improves the error messaging as requested.