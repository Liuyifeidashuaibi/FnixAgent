import re
import time
from datetime import datetime


def parse_http_date(date_string):
    """
    Parse an HTTP date string and return a datetime object.
    """
    # RFC 1123 format: "Sun, 06 Nov 1994 08:49:37 GMT"
    rfc1123_match = re.match(r'^([A-Za-z]{3}),\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})\s+GMT$', date_string)
    if rfc1123_match:
        day, month, year, hour, minute, second = rfc1123_match.groups()
        # Convert month name to number
        months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                  'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
        month_num = months.get(month, 1)
        try:
            return datetime(int(year), month_num, int(day), int(hour), int(minute), int(second))
        except ValueError:
            return None
    
    # RFC 850 format: "Sunday, 06-Nov-94 08:49:37 GMT"
    rfc850_match = re.match(r'^[A-Za-z]+,\s+(\d{1,2})-([A-Za-z]{3})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s+GMT$', date_string)
    if rfc850_match:
        day, month, year, hour, minute, second = rfc850_match.groups()
        months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                  'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
        month_num = months.get(month, 1)
        
        # RFC 7231: two-digit years must be interpreted relative to current year
        # If the parsed year appears to be more than 50 years in the future, use past century
        two_digit_year = int(year)
        current_year = datetime.now().year
        current_century = current_year // 100 * 100
        
        # Calculate candidate years
        year_2000s = current_century + two_digit_year
        year_1900s = current_century - 100 + two_digit_year
        
        # Choose the year that is closest to current year but not more than 50 years in future
        if abs(year_2000s - current_year) <= 50:
            full_year = year_2000s
        elif abs(year_1900s - current_year) <= 50:
            full_year = year_1900s
        else:
            # Fall back to standard interpretation: 0-69 -> 2000-2069, 70-99 -> 1970-1999
            # But per RFC 7231, we should use the rule: >50 years in future -> most recent past year
            if two_digit_year <= 99:
                # Check if year_2000s is >50 years in future
                if year_2000s > current_year + 50:
                    full_year = year_1900s
                else:
                    full_year = year_2000s
            else:
                full_year = two_digit_year
        
        try:
            return datetime(full_year, month_num, int(day), int(hour), int(minute), int(second))
        except ValueError:
            return None
    
    # ANSI C asctime() format: "Sun Nov  6 08:49:37 1994"
    asctime_match = re.match(r'^[A-Za-z]{3}\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+(\d{4})$', date_string)
    if asctime_match:
        month, day, hour, minute, second, year = asctime_match.groups()
        months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                  'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
        month_num = months.get(month, 1)
        try:
            return datetime(int(year), month_num, int(day), int(hour), int(minute), int(second))
        except ValueError:
            return None
    
    return None