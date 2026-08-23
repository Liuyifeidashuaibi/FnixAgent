"""
Fixed polyoptions.py to handle domain specifications like 'RR[y,z]'

This addresses the issue where Poly(1.2*x*y*z, x, domain='RR[y,z]') 
raises an OptionError because the domain format is not recognized.
"""

from sympy.polys.domains import ZZ, QQ, RR, CC, GF
from sympy.polys.domains.polynomialring import PolynomialRing
from sympy.polys.options import OptionError

def preprocess_domain(domain):
    """
    Preprocess domain specification to handle formats like 'RR[y,z]'.
    
    This function extends the original preprocessing logic to support
    polynomial ring specifications over base domains.
    """
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
        
        # Handle simple domains
        simple_domains = {
            'ZZ': ZZ,
            'QQ': QQ,
            'RR': RR,
            'CC': CC,
            'GF': GF
        }
        
        if domain in simple_domains:
            return simple_domains[domain]
    
    # If we can't parse it, return it as-is (let the caller handle the error)
    return domain

class Options:
    def __init__(self, gens, args, flags=None, strict=True):
        self._args = args
        self._gens = gens
        self._flags = flags or {}
        self._strict = strict
        
        # Process domain option with improved error handling
        if 'domain' in args:
            try:
                self['domain'] = preprocess_domain(args['domain'])
            except Exception as e:
                if strict:
                    raise OptionError(
                        f"Domain '{args['domain']}' is not valid. "
                        f"Supported formats include: 'RR', 'QQ', 'ZZ', 'CC', 'GF', "
                        f"and polynomial rings like 'RR[x,y]', 'QQ[t]', etc. "
                        f"Original error: {e}"
                    )
                else:
                    self['domain'] = args['domain']
        
    def __setitem__(self, key, value):
        setattr(self, key, value)
        
    def __getitem__(self, key):
        return getattr(self, key)
        
    def preprocess_options(self, args):
        """Preprocess all options with improved error messages."""
        for option, value in args.items():
            if value is not None and hasattr(self, f'preprocess_{option}'):
                try:
                    preprocess_method = getattr(self, f'preprocess_{option}')
                    self[option] = preprocess_method(value)
                except Exception as e:
                    raise OptionError(
                        f"Error processing {option}='{value}': {e}"
                    )

def build_options(gens, args):
    """Build options from generators and arguments."""
    if len(args) != 1 or 'opt' not in args or gens:
        return Options(gens, args)
    else:
        return args['opt']