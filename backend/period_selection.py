"""Extract a single explicit reference month without inventing a date range."""
import re

def requested_month(question):
 months=set(f'{int(y):04d}-{int(m):02d}' for y,m in re.findall(r'(20[0-9]{2})\s*(?:년\s*|-)\s*(0?[1-9]|1[0-2])(?:월|\b)',question or ''))
 return next(iter(months)) if len(months)==1 else None
