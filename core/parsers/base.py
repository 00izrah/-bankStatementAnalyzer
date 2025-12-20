"""
Base parser class for bank statements.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any
import pdfplumber
import re

class BaseStatementParser(ABC):
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.transactions = []

    def parse(self) -> List[Dict[str, Any]]:
        """Parse the PDF and return a list of transactions."""
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                self.parse_page(text)
        return self.transactions

    @abstractmethod
    def parse_page(self, text: str) -> None:
        """Parse a single page of text and extract transactions."""
        pass

    def clean_amount(self, amount_str: str) -> Decimal:
        """Convert amount string to Decimal."""
        # Remove currency symbols and commas
        cleaned = re.sub(r'[₦,]', '', amount_str.strip())
        return Decimal(cleaned)

    def parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime object with extensive format support."""
        try:
            # Clean the date string
            date_str = date_str.strip().upper()
            
            # Try common date formats (most common first for efficiency)
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
            ]
            
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    
                    # Handle 2-digit year ambiguity
                    # If year is in the future by more than 1 year, assume it's in the past century
                    if parsed_date.year > datetime.now().year + 1:
                        parsed_date = parsed_date.replace(year=parsed_date.year - 100)
                    
                    return parsed_date
                except ValueError:
                    continue
            
            # If all formats fail, try to be more flexible
            # Replace common separators with a standard one and try again
            for separator in ['/', '.', ' ']:
                if separator in date_str:
                    normalized = date_str.replace(separator, '-')
                    for fmt in ['%d-%b-%y', '%d-%b-%Y', '%d-%m-%Y', '%d-%m-%y']:
                        try:
                            return datetime.strptime(normalized, fmt)
                        except ValueError:
                            continue
            
            raise ValueError(f"Could not parse date: {date_str}")
        except Exception as e:
            raise ValueError(f"Error parsing date '{date_str}': {str(e)}")

    def categorize_transaction(self, description: str) -> str:
        """
        Categorize transaction based on description with improved Nigerian context.
        """
        description = description.lower()
        
        categories = {
            'food': [
                'restaurant', 'cafe', 'food', 'grocery', 'supermarket',
                'burger', 'pizza', 'chicken', 'market', 'shoprite', 'spar',
                'eatery', 'cuisine', 'bakery', 'meat', 'fruit', 'vegetable'
            ],
            'transport': [
                'uber', 'bolt', 'taxi', 'transport', 'fuel', 'petrol',
                'bus', 'train', 'flight', 'airline', 'cab', 'ride',
                'parking', 'toll', 'vehicle', 'car'
            ],
            'utilities': [
                'electricity', 'water', 'gas', 'dstv', 'gotv', 'internet',
                'wifi', 'phone', 'mobile', 'utility', 'startimes', 'nepa',
                'ikeja electric', 'ekedc', 'phcn', 'mtn', 'glo', 'airtel', '9mobile'
            ],
            'entertainment': [
                'cinema', 'movie', 'theatre', 'netflix', 'spotify',
                'game', 'betting', 'entertainment', 'bet', 'sport', 'gym',
                'recreation', 'club', 'bar', 'lounge'
            ],
            'shopping': [
                'mall', 'store', 'shop', 'retail', 'clothing', 'fashion',
                'electronics', 'gadget', 'amazon', 'jumia', 'konga',
                'purchase', 'boutique', 'shoes', 'accessories'
            ],
            'health': [
                'hospital', 'clinic', 'pharmacy', 'medical', 'doctor',
                'dental', 'health', 'drug', 'medicine', 'laboratory',
                'test', 'injection', 'treatment'
            ],
            'education': [
                'school', 'college', 'university', 'tuition', 'course',
                'training', 'education', 'book', 'academy', 'institute',
                'lesson', 'exam', 'textbook'
            ],
            'transfer': [
                'transfer', 'send', 'remittance', 'ussd', 'nip', 'rtgs',
                'instant transfer', 'mobile transfer'
            ],
            'atm': [
                'atm', 'withdrawal', 'cash'
            ],
            'fees': [
                'charge', 'fee', 'commission', 'stamp duty', 'sms charge',
                'maintenance', 'vat', 'bank charge'
            ],
            'salary': [
                'salary', 'wage', 'income', 'payroll', 'stipend', 'allowance'
            ]
        }

        # Check each category
        for category, keywords in categories.items():
            if any(keyword in description for keyword in keywords):
                return category
        
        return 'other'