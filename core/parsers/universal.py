"""
Universal parser for Nigerian bank statements.
This parser attempts to extract transactions from any bank statement format.
"""
from .base import BaseStatementParser
import re
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional

class UniversalBankParser(BaseStatementParser):
    """
    A flexible parser that works with most Nigerian bank statement formats.
    It uses multiple patterns to detect transactions.
    """
    
    def __init__(self, pdf_path: str):
        super().__init__(pdf_path)
        self.seen_transactions = set()  # Track unique transactions to avoid duplicates
        self.previous_balance = None  # Track previous balance for validation
        self.balance_errors = 0  # Count balance inconsistencies
    
    def parse_page(self, text: str) -> None:
        """Parse bank statement page using multiple patterns."""
        lines = text.split('\n')
        
        # First pass: identify if this is a columnar statement
        is_columnar = self._is_columnar_format(lines)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Skip empty lines and headers
            if not line.strip() or self._is_header(line):
                i += 1
                continue
            
            # Try column-based parsing first for structured statements
            if is_columnar:
                transaction = self._parse_columnar(line)
                if transaction:
                    if self._validate_and_add_transaction(transaction):
                        i += 1
                        continue
            
            # Check if description spans multiple lines
            combined_line = line
            if i + 1 < len(lines) and not self._looks_like_transaction_start(lines[i + 1]):
                combined_line = line + " " + lines[i + 1].strip()
            
            # Try different parsing patterns
            transaction = (
                self._parse_pattern_1(combined_line) or
                self._parse_pattern_2(combined_line) or
                self._parse_pattern_3(combined_line) or
                self._parse_pattern_4(combined_line) or
                self._parse_pattern_5(combined_line)  # New pattern
            )
            
            if transaction:
                if self._validate_and_add_transaction(transaction):
                    # Skip next line if we combined lines
                    if combined_line != line:
                        i += 1
            
            i += 1
    
    def _is_columnar_format(self, lines: List[str]) -> bool:
        """Detect if statement uses a columnar format."""
        # Look for consistent spacing patterns in first 20 lines
        for line in lines[:20]:
            if re.search(r'\d{2}[-/]\w{3}[-/]\d{2,4}\s+.{20,}\s+[\d,]+\.\d{2}\s+[\d,]+\.\d{2}\s+[\d,]+\.\d{2}', line, re.IGNORECASE):
                return True
        return False
    
    def _looks_like_transaction_start(self, line: str) -> bool:
        """Check if line looks like the start of a transaction."""
        # A line starting with a date is likely a new transaction
        return bool(re.match(r'^\d{2}[-/]\w{3}[-/]\d{2,4}', line, re.IGNORECASE))
    
    def _validate_and_add_transaction(self, transaction: Dict[str, Any]) -> bool:
        """Validate transaction and add if unique."""
        # Create a unique key for the transaction
        trans_key = (
            transaction['date'].isoformat(),
            transaction['description'].strip()[:50],  # Limit description length for key
            str(abs(transaction['amount']))
        )
        
        # Check for duplicates
        if trans_key in self.seen_transactions:
            return False
        
        # Validate balance if available
        if transaction.get('balance') and transaction['balance'] != Decimal('0'):
            if self.previous_balance is not None:
                expected_balance = self.previous_balance + transaction['amount']
                actual_balance = transaction['balance']
                
                # Allow small rounding differences (1 kobo)
                if abs(expected_balance - actual_balance) > Decimal('0.01'):
                    self.balance_errors += 1
                    # Still add transaction, but note the inconsistency
                    print(f"⚠️  Balance mismatch: Expected {expected_balance}, Got {actual_balance}")
            
            self.previous_balance = transaction['balance']
        
        # Add transaction
        self.seen_transactions.add(trans_key)
        self.transactions.append(transaction)
        return True
    
    def _parse_columnar(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Parse columnar format statements with fixed-width columns.
        This is more accurate for well-structured statements.
        """
        # Pattern for: Date Description Debit Credit Balance
        pattern = r'(\d{2}[-/]\w{3}[-/]\d{2,4})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$'
        match = re.search(pattern, line, re.IGNORECASE)
        
        if match:
            try:
                date_str, description, col1, col2, balance_str = match.groups()
                
                date = self.parse_date(date_str)
                balance = self.clean_amount(balance_str)
                
                # Determine which column is debit/credit based on values
                val1 = self.clean_amount(col1)
                val2 = self.clean_amount(col2)
                
                # Usually: non-zero column is the transaction, other is 0.00
                if val1 > 0 and val2 == 0:
                    amount = -val1  # First column is debit
                elif val2 > 0 and val1 == 0:
                    amount = val2   # Second column is credit
                elif val1 > val2:
                    amount = -val1  # Larger value is likely the debit
                else:
                    amount = val2   # Larger value is likely the credit
                
                return {
                    'date': date,
                    'description': description.strip(),
                    'amount': amount,
                    'balance': balance,
                    'category': None
                }
            except Exception as e:
                pass
        
        return None
    
    def _is_header(self, line: str) -> bool:
        """Check if line is a header or non-transaction metadata."""
        headers = [
            'date', 'value date', 'transaction date', 'posting date',
            'description', 'narration', 'details', 'remarks',
            'debit', 'credit', 'withdrawal', 'deposit',
            'balance', 'running balance', 'available balance',
            'account number', 'statement', 'period', 'opening balance',
            'closing balance', 'total', 'page', 'continued'
        ]
        line_lower = line.lower()
        
        # Check for headers
        if any(header in line_lower for header in headers):
            # But not if it's an actual transaction description containing these words
            if not re.search(r'\d{2}[-/]\w{3}[-/]\d{2,4}', line, re.IGNORECASE):
                return True
        
        return False
    
    def _parse_pattern_1(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Pattern 1: DD-MMM-YY Description Amount Balance
        Example: 04-AUG-25 AROWOJOLU, OLUWAGBEMIGA 1,000.00 1,035.60
        Improved to handle various spacing and amount formats.
        """
        # More flexible pattern that captures everything between date and final numbers
        pattern = r'(\d{2}[-/][A-Z]{3}[-/]\d{2,4})\s+(.+?)\s+([-+]?[\d,]+\.\d{2})\s+([-+]?[\d,]+\.\d{2})\s*$'
        match = re.search(pattern, line, re.IGNORECASE)
        
        if match:
            try:
                date_str, description, amount_str, balance_str = match.groups()
                
                # Clean description (remove extra spaces, dashes)
                description = re.sub(r'\s+', ' ', description).strip()
                description = re.sub(r'^[-\s]+|[-\s]+$', '', description)
                
                date = self.parse_date(date_str)
                amount = self._parse_amount(amount_str, description)
                balance = self.clean_amount(balance_str)
                
                # Validate that balance is reasonable
                if balance < 0:
                    balance = abs(balance)
                
                return {
                    'date': date,
                    'description': description,
                    'amount': amount,
                    'balance': balance,
                    'category': None
                }
            except Exception as e:
                # Silent fail for this pattern, try others
                pass
        
        return None
    
    def _parse_pattern_2(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Pattern 2: DD/MM/YYYY Description Debit Credit Balance
        Example: 04/08/2025 Transfer 1,000.00 0.00 1,035.60
        Improved debit/credit detection.
        """
        pattern = r'(\d{2}[/-]\d{2}[/-]\d{2,4})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$'
        match = re.search(pattern, line)
        
        if match:
            try:
                date_str, description, col1_str, col2_str, balance_str = match.groups()
                
                description = re.sub(r'\s+', ' ', description).strip()
                date = self.parse_date(date_str)
                
                # Parse amounts
                col1 = self.clean_amount(col1_str)
                col2 = self.clean_amount(col2_str)
                balance = self.clean_amount(balance_str)
                
                # Determine which is debit/credit
                # Usually: debit is first, credit is second
                # One should be 0.00 or close to it
                if col1 > 0 and col2 == 0:
                    amount = -col1  # Debit
                elif col2 > 0 and col1 == 0:
                    amount = col2   # Credit
                elif col1 > col2:
                    # If both have values, larger one is likely the transaction
                    amount = -col1 if self._is_likely_debit(description) else col1
                else:
                    amount = col2 if not self._is_likely_debit(description) else -col2
                
                return {
                    'date': date,
                    'description': description,
                    'amount': amount,
                    'balance': balance,
                    'category': None
                }
            except Exception as e:
                pass
        
        return None
    
    def _parse_pattern_3(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Pattern 3: Date Description Amount (with +/- sign)
        Example: 04-AUG-25 Payment -1,000.00 Balance: 1,035.60
        Improved balance extraction.
        """
        pattern = r'(\d{2}[-/][A-Z]{3}[-/]\d{2,4})\s+(.+?)\s+([-+][\d,]+\.\d{2})'
        match = re.search(pattern, line, re.IGNORECASE)
        
        if match:
            try:
                date_str, description, amount_str = match.groups()
                
                description = re.sub(r'\s+', ' ', description).strip()
                date = self.parse_date(date_str)
                amount = self.clean_amount(amount_str)
                
                # Try to find balance after the amount
                remainder = line[match.end():].strip()
                balance_match = re.search(r'([\d,]+\.\d{2})', remainder)
                balance = self.clean_amount(balance_match.group(1)) if balance_match else Decimal('0')
                
                return {
                    'date': date,
                    'description': description,
                    'amount': amount,
                    'balance': balance,
                    'category': None
                }
            except Exception as e:
                pass
        
        return None
    
    def _parse_pattern_4(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Pattern 4: Multiple dates on same line (Value Date and Transaction Date)
        Example: 04-AUG-25 04-AUG-25 Opening Balance 0.00 35.60
        Improved to handle various formats.
        """
        pattern = r'(\d{2}[-/][A-Z]{3}[-/]\d{2,4})\s+\d{2}[-/][A-Z]{3}[-/]\d{2,4}\s+(.+?)\s+([-]?\s*[\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$'
        match = re.search(pattern, line, re.IGNORECASE)
        
        if match:
            try:
                date_str, description, amount_str, balance_str = match.groups()
                
                description = re.sub(r'\s+', ' ', description).strip()
                date = self.parse_date(date_str)
                amount = self._parse_amount(amount_str, description)
                balance = self.clean_amount(balance_str)
                
                return {
                    'date': date,
                    'description': description,
                    'amount': amount,
                    'balance': balance,
                    'category': None
                }
            except Exception as e:
                pass
        
        return None
    
    def _parse_pattern_5(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Pattern 5: Simplified pattern for basic statements
        Example: 04-AUG-25 Description 1000.00
        For statements without explicit balance columns.
        """
        pattern = r'(\d{2}[-/]\w{3}[-/]\d{2,4})\s+(.+?)\s+([\d,]+\.\d{2})\s*$'
        match = re.search(pattern, line, re.IGNORECASE)
        
        if match:
            try:
                date_str, description, amount_str = match.groups()
                
                description = re.sub(r'\s+', ' ', description).strip()
                date = self.parse_date(date_str)
                amount = self._parse_amount(amount_str, description)
                
                return {
                    'date': date,
                    'description': description,
                    'amount': amount,
                    'balance': Decimal('0'),  # No balance info
                    'category': None
                }
            except Exception as e:
                pass
        
        return None
    
    def _is_likely_debit(self, description: str) -> bool:
        """Check if description indicates a debit transaction."""
        debit_keywords = [
            'withdrawal', 'payment', 'transfer', 'debit', 'charge', 'fee',
            'purchase', 'atm', 'pos', 'web', 'commission', 'stamp duty',
            'purchase', 'bill', 'airtime', 'data', 'subscription'
        ]
        
        description_lower = description.lower()
        return any(keyword in description_lower for keyword in debit_keywords)
    
    def _parse_amount(self, amount_str: str, description: str) -> Decimal:
        """
        Parse amount and determine if it's debit or credit based on context.
        Improved logic with better keyword detection.
        """
        # Clean and convert to Decimal
        amount = self.clean_amount(amount_str)
        
        # If amount string explicitly has minus sign, respect it
        if '-' in amount_str:
            return -abs(amount)
        
        # Check for credit indicators (incoming money)
        credit_keywords = [
            'credit', 'deposit', 'salary', 'reversal', 'refund',
            'interest', 'dividend', 'inflow', 'received'
        ]
        
        description_lower = description.lower()
        is_credit = any(keyword in description_lower for keyword in credit_keywords)
        
        # If explicitly a credit, ensure positive
        if is_credit:
            return abs(amount)
        
        # Check for debit indicators (outgoing money)
        if self._is_likely_debit(description):
            return -abs(amount)
        
        # Default: if no clear indicator, assume positive (credit)
        return amount
    
    def get_parsing_stats(self) -> Dict[str, Any]:
        """Return parsing statistics for debugging."""
        return {
            'total_transactions': len(self.transactions),
            'balance_errors': self.balance_errors,
            'duplicates_prevented': len(self.seen_transactions) - len(self.transactions)
        }
