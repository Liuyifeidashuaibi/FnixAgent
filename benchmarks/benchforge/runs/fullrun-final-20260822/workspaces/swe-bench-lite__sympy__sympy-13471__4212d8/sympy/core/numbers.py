# Fix for Python 2->3 pickle compatibility
# Replace: num[1] = long(num[1], 16)
# With:   num[1] = int(num[1].rstrip('L'), 16)
# This handles Python 2's '1L' long integer notation in pickle data.
