from sympy.polys.domains import ZZ, QQ, RR, CC, GF
from sympy.polys.domains.polynomialring import PolynomialRing
from sympy.polys.domains.realfield import RealField
from sympy.polys.domains.complexfield import ComplexField
from sympy.polys.domains.finitefield import FiniteField
from sympy.polys.domains.rationalfield import RationalField
from sympy.polys.domains.integerring import IntegerRing
from sympy.polys.domains.algebraicfield import AlgebraicField
from sympy.polys.domains.expressiondomain import ExpressionDomain
from sympy.polys.options import OptionError

def preprocess_domain(domain):
    """Preprocess domain specification."""
    if domain is None:
        return None
    
    # Handle string domains like 'RR[y,z]'
    if isinstance(domain, str):
        domain = domain.strip()
        
        # Handle polynomial rings over base domains
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
    
    return domain

class Options:
    def __init__(self, gens, args, flags=None, strict=True):
        self._args = args
        self._gens = gens
        self._flags = flags or {}
        self._strict = strict
        
        # Initialize default options
        self.defaults = {}
        
        # Process domain option
        if 'domain' in args:
            self['domain'] = preprocess_domain(args['domain'])
        
    def __setitem__(self, key, value):
        setattr(self, key, value)
        
    def __getitem__(self, key):
        return getattr(self, key)
        
    def preprocess_options(self, args):
        """Preprocess all options."""
        for option, value in args.items():
            if value is not None and hasattr(self, f'preprocess_{option}'):
                preprocess_method = getattr(self, f'preprocess_{option}')
                self[option] = preprocess_method(value)

def build_options(gens, args):
    """Build options from generators and arguments."""
    if len(args) != 1 or 'opt' not in args or gens:
        return Options(gens, args)
    else:
        return args['opt']