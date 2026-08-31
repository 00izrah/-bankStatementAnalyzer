"""
Base parser class for bank statements.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
import pdfplumber
import re


class BaseStatementParser(ABC):
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.transactions: List[Dict[str, Any]] = []
        self._detected_date_format: Optional[str] = None

    def parse(self) -> List[Dict[str, Any]]:
        """Parse the PDF and return a list of transactions."""
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    self.parse_page(text)
        return self.transactions

    @abstractmethod
    def parse_page(self, text: str) -> None:
        """Parse a single page of text and extract transactions."""
        pass

    def clean_amount(self, amount_str: str) -> Decimal:
        """Convert amount string to Decimal handling currencies, DR/CR, parentheses, and commas."""
        if not amount_str:
            return Decimal('0')
        cleaned = str(amount_str).strip()
        if not cleaned or cleaned in ('-', '--', 'N/A', 'nil', 'null'):
            return Decimal('0')

        # Check for parentheses indicating negative amount: (1,234.50)
        is_negative = False
        if cleaned.startswith('(') and cleaned.endswith(')'):
            is_negative = True
            cleaned = cleaned[1:-1]
        elif cleaned.endswith('-') or cleaned.startswith('-'):
            is_negative = True
            cleaned = cleaned.replace('-', '')
        elif 'dr' in cleaned.lower():
            is_negative = True
            cleaned = re.sub(r'(?i)dr', '', cleaned)
        elif 'cr' in cleaned.lower():
            cleaned = re.sub(r'(?i)cr', '', cleaned)

        # Remove currency symbols (₦, NGN, $, £, €), letters, and spaces
        cleaned = re.sub(r'[^\d.]', '', cleaned)
        if not cleaned:
            return Decimal('0')

        # Handle multiple dots (e.g. 1.200.50 -> 1200.50)
        if cleaned.count('.') > 1:
            parts = cleaned.split('.')
            cleaned = ''.join(parts[:-1]) + '.' + parts[-1]

        val = Decimal(cleaned)
        return -val if is_negative else val

    def parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime object with optimized format caching."""
        if not date_str:
            raise ValueError("Empty date string")
        # Extract the date part if time or extra text is present
        date_str = str(date_str).strip().upper()
        # If timestamp is attached, e.g. "04-AUG-2025 14:32:00"
        date_str = re.split(r'\s{2,}|\s+(?=\d{1,2}:)', date_str)[0].strip()

        current_year = datetime.now().year

        # 1. Try cached successful format first
        if self._detected_date_format:
            try:
                parsed_date = datetime.strptime(date_str, self._detected_date_format)
                if parsed_date.year > current_year + 1:
                    parsed_date = parsed_date.replace(year=parsed_date.year - 100)
                return parsed_date
            except ValueError:
                pass

        # 2. Common formats ordered by frequency in Nigerian bank statements
        formats = [
            '%d-%b-%y',      # 04-AUG-25 (most common in Nigerian statements)
            '%d-%b-%Y',      # 04-AUG-2025
            '%d/%m/%Y',      # 04/08/2025
            '%d/%m/%y',      # 04/08/25
            '%d-%m-%Y',      # 04-08-2025
            '%d-%m-%y',      # 04-08-25
            '%d.%m.%Y',      # 04.08.2025
            '%d.%m.%y',      # 04.08.25
            '%Y-%m-%d',      # 2025-08-04 (ISO format)
            '%d-%B-%Y',      # 04-AUGUST-2025
            '%d-%B-%y',      # 04-AUGUST-25
            '%d %b %Y',      # 04 AUG 2025
            '%d %b %y',      # 04 AUG 25
            '%d %B %Y',      # 04 AUGUST 2025
            '%d %B %y',      # 04 AUGUST 25
            '%Y/%m/%d',      # 2025/08/04
        ]

        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                if parsed_date.year > current_year + 1:
                    parsed_date = parsed_date.replace(year=parsed_date.year - 100)
                self._detected_date_format = fmt
                return parsed_date
            except ValueError:
                continue

        # 3. Fallback for non-standard separators
        for separator in ['/', '.', ' ']:
            if separator in date_str:
                normalized = date_str.replace(separator, '-')
                for fmt in ['%d-%b-%y', '%d-%b-%Y', '%d-%m-%Y', '%d-%m-%y', '%Y-%m-%d']:
                    try:
                        parsed = datetime.strptime(normalized, fmt)
                        if parsed.year > current_year + 1:
                            parsed = parsed.replace(year=parsed.year - 100)
                        return parsed
                    except ValueError:
                        continue

        raise ValueError(f"Could not parse date: '{date_str}'")