from sympy.core.basic import Basic
from sympy.core.compatibility import as_int, range
from sympy.utilities.iterables import flatten


class Permutation(Basic):
    """
    A permutation in cyclic notation.
    """
    
    def __init__(self, *cyclic_form, **kwargs):
        # Handle the case where a single list of cycles is passed
        if len(cyclic_form) == 1 and isinstance(cyclic_form[0], list):
            cycles = cyclic_form[0]
        else:
            cycles = list(cyclic_form)
        
        # Convert to standard form: list of tuples
        self._cycles = []
        for cycle in cycles:
            if isinstance(cycle, (list, tuple)):
                self._cycles.append(tuple(cycle))
            else:
                raise ValueError("Each cycle must be a list or tuple")
        
        # Process cycles left-to-right to handle non-disjoint cycles
        # Start with identity permutation
        self._array_form = None
        self._size = 0
        
        # Calculate size and build permutation
        if self._cycles:
            # Find maximum element to determine size
            max_elem = max(max(cycle) for cycle in self._cycles if cycle)
            self._size = max_elem + 1
            
            # Start with identity
            perm = list(range(self._size))
            
            # Apply each cycle left-to-right
            for cycle in self._cycles:
                if not cycle:
                    continue
                # Apply this cycle to the current permutation
                temp = perm[:]
                for i in range(len(cycle)):
                    src = cycle[i]
                    dst = cycle[(i + 1) % len(cycle)]
                    if src < len(temp) and dst < len(temp):
                        temp[dst] = perm[src]
                perm = temp
            
            self._array_form = perm
        else:
            self._array_form = []
            self._size = 0
    
    def __repr__(self):
        return f"Permutation({self._cycles})"

    @property
    def array_form(self):
        return self._array_form

    @property
    def size(self):
        return self._size
