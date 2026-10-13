"""Handler registry. Implementations in rules_impl.py."""
from .rules_impl import ORDER, safe

HANDLERS = [safe(h) for h in ORDER]
