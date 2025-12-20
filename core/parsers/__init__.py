"""
Bank statement parser package.
"""

from .base import BaseStatementParser
from .universal import UniversalBankParser

# Use universal parser for all banks
BANK_PARSERS = {
    'universal': UniversalBankParser,
}