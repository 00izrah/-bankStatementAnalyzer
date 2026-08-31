"""
Bank statement parser package supporting PDF, Excel (.xlsx, .xls), and CSV (.csv).
"""
import os
from .base import BaseStatementParser
from .universal import UniversalBankParser
from .spreadsheet import SpreadsheetStatementParser


BANK_PARSERS = {
    'universal': UniversalBankParser,
    'spreadsheet': SpreadsheetStatementParser,
}


def get_parser_for_file(file_path: str):
    """Return the optimal parser class for the given file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ('.xlsx', '.xls', '.csv'):
        return SpreadsheetStatementParser
    return UniversalBankParser