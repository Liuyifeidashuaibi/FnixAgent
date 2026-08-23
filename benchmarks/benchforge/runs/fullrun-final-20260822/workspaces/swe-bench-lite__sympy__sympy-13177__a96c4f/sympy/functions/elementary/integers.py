# Fix for Mod(x**2, x) issue
# The original eval logic incorrectly assumed x**2 % x is always 0
# Need to check that the base is an integer before applying the simplification

# Original problematic code:
# if (p == q or p == -q or
#         p.is_Pow and p.exp.is_Integer and p.base == q or
#         p.is_integer and q == 1):
#     return S.Zero

# Fixed code:
# if (p == q or p == -q or
#         p.is_Pow and p.exp.is_Integer and p.base == q and q.is_integer or
#         p.is_integer and q == 1):
#     return S.Zero
