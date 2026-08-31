"""
Universal parser for Nigerian bank statements.
Implements a 3-tier hybrid strategy:
1. Table-based extraction (for native grid / structured table PDFs)
2. Multi-line block stream collector (for borderless multi-line statements)
3. Pattern-based line-by-line fallback
With mathematical running-balance reconciliation.
"""
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
import pdfplumber
from .base import BaseStatementParser

logger = logging.getLogger('bankstatements')


class UniversalBankParser(BaseStatementParser):
    """
    A robust, universal parser tailored for Nigerian bank statement formats
    (GTBank, Access Bank, Zenith, UBA, FirstBank, Kuda, Moniepoint, OPay, Stanbic, FCMB, etc.).
    """

    DATE_PATTERN = re.compile(
        r'^\s*(\d{1,2}[-/.](?:[A-Za-z]{3,9}|\d{1,2})[-/.](?:\d{4}|\d{2}))'
    )

    def __init__(self, pdf_path: str):
        super().__init__(pdf_path)
        self.seen_transactions = set()
        self.balance_errors = 0
        self.strategy_used = None

    def parse(self) -> List[Dict[str, Any]]:
        """
        Execute the 3-tier parsing strategy pipeline.
        """
        with pdfplumber.open(self.pdf_path) as pdf:
            # 1. Try Table-based extraction first
            parsed_tables = self._parse_with_table_extractor(pdf)
            if parsed_tables and len(parsed_tables) > 0:
                self.strategy_used = 'table_extractor'
                self.transactions = parsed_tables
            else:
                # 2. Try Multi-line block stream collector
                parsed_blocks = self._parse_with_block_collector(pdf)
                if parsed_blocks and len(parsed_blocks) > 0:
                    self.strategy_used = 'block_collector'
                    self.transactions = parsed_blocks
                else:
                    # 3. Fallback: line-by-line text parsing
                    self.strategy_used = 'line_patterns'
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            self.parse_page(text)

        # 4. Apply mathematical balance reconciliation
        self._reconcile_running_balances()
        return self.transactions

    def parse_page(self, text: str) -> None:
        """Fallback line-by-line parser when higher-tier extractors fail."""
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or self._is_header(line):
                i += 1
                continue

            # Check if description spans 2-3 lines
            combined_line = line
            lookahead = 1
            while lookahead <= 2 and (i + lookahead) < len(lines):
                next_line = lines[i + lookahead].strip()
                if next_line and not self.DATE_PATTERN.match(next_line):
                    combined_line += " " + next_line
                    lookahead += 1
                else:
                    break

            txn = self._parse_line_regex(combined_line)
            if txn and self._validate_and_add_transaction(txn):
                i += lookahead
            else:
                i += 1

    # -------------------------------------------------------------------------
    # Strategy 1: Table-based Extractor
    # -------------------------------------------------------------------------
    def _parse_with_table_extractor(self, pdf) -> List[Dict[str, Any]]:
        """Extract transactions directly from structured table grids."""
        extracted = []

        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                if not table or len(table) < 2:
                    continue

                col_map = self._detect_table_columns(table[0])
                if not col_map or 'date' not in col_map:
                    # Check if second row is the actual header
                    col_map = self._detect_table_columns(table[1])
                    start_row = 2 if col_map and 'date' in col_map else None
                else:
                    start_row = 1

                if not col_map or 'date' not in col_map:
                    continue

                for row in table[start_row:]:
                    if not row or not any(row):
                        continue

                    txn = self._extract_transaction_from_table_row(row, col_map)
                    if txn:
                        trans_key = (
                            txn['date'].isoformat(),
                            txn['description'][:60],
                            str(abs(txn['amount']))
                        )
                        if trans_key not in self.seen_transactions:
                            self.seen_transactions.add(trans_key)
                            extracted.append(txn)

        return extracted

    def _detect_table_columns(self, header_row: List[Optional[str]]) -> Optional[Dict[str, int]]:
        """Identify column index mapping from table headers."""
        if not header_row:
            return None

        col_map = {}
        cleaned_headers = [
            re.sub(r'[\r\n\s]+', ' ', str(cell or '')).strip().lower()
            for cell in header_row
        ]

        for idx, h in enumerate(cleaned_headers):
            if not h:
                continue
            if any(k in h for k in ['trans date', 'txn date', 'tx date', 'post date', 'value date', 'date']):
                if 'date' not in col_map or 'trans' in h or 'txn' in h:
                    col_map['date'] = idx
            elif any(k in h for k in ['narrat', 'particular', 'description', 'detail', 'remarks', 'memo', 'tran details']):
                col_map['description'] = idx
            elif any(k in h for k in ['debit', 'withdrawal', 'dr amount', 'dr', 'money out', 'debit (ngn)']):
                col_map['debit'] = idx
            elif any(k in h for k in ['credit', 'deposit', 'cr amount', 'cr', 'money in', 'credit (ngn)']):
                col_map['credit'] = idx
            elif any(k in h for k in ['balance', 'bal', 'closing balance', 'ledger balance']):
                col_map['balance'] = idx
            elif 'amount' in h and 'debit' not in col_map and 'credit' not in col_map:
                col_map['amount'] = idx

        # Need at least Date and one financial column (Amount, Debit, Credit, or Balance)
        has_amount_col = any(k in col_map for k in ['debit', 'credit', 'amount', 'balance'])
        if 'date' in col_map and has_amount_col:
            # If description column wasn't explicitly matched, pick the widest text column
            if 'description' not in col_map:
                for idx in range(len(header_row)):
                    if idx not in col_map.values():
                        col_map['description'] = idx
                        break
            return col_map

        return None

    def _extract_transaction_from_table_row(
        self,
        row: List[Optional[str]],
        col_map: Dict[str, int]
    ) -> Optional[Dict[str, Any]]:
        """Parse a single table row using detected column mapping."""
        try:
            date_cell = row[col_map['date']] if col_map['date'] < len(row) else None
            if not date_cell:
                return None

            date_str = str(date_cell).strip()
            date = self.parse_date(date_str)

            # Extract Narration / Description across mapped cell and fallback unmapped text cells
            desc_parts = []
            if 'description' in col_map and col_map['description'] < len(row):
                desc_val = row[col_map['description']]
                if desc_val and str(desc_val).strip():
                    desc_parts.append(str(desc_val).strip())

            # If description is still empty or too short, gather all other non-numeric, non-date cells in the row
            if not desc_parts or len(" ".join(desc_parts).strip()) < 3:
                for idx, cell in enumerate(row):
                    if idx not in (col_map.get('date'), col_map.get('debit'), col_map.get('credit'), col_map.get('amount'), col_map.get('balance')):
                        if cell is not None:
                            val = str(cell).strip()
                            if val and not re.match(r'^\d+$', val) and not re.match(r'^[\d,.-]+$', val):
                                desc_parts.append(val)

            description = re.sub(r'[\r\n\s]+', ' ', " ".join(desc_parts)).strip()
            if not description or description.lower() in ('none', 'null', 'nil', '-', 'n/a'):
                description = "Bank Transaction"

            # Balance
            balance = Decimal('0.00')
            if 'balance' in col_map and col_map['balance'] < len(row):
                bal_cell = row[col_map['balance']]
                if bal_cell:
                    balance = self.clean_amount(str(bal_cell))

            # Amounts (Separate Debit / Credit vs Single Amount)
            amount = Decimal('0.00')
            if 'debit' in col_map and 'credit' in col_map:
                dr_cell = row[col_map['debit']] if col_map['debit'] < len(row) else None
                cr_cell = row[col_map['credit']] if col_map['credit'] < len(row) else None

                dr_val = abs(self.clean_amount(str(dr_cell or '')))
                cr_val = abs(self.clean_amount(str(cr_cell or '')))

                if dr_val > 0 and cr_val == 0:
                    amount = -dr_val
                elif cr_val > 0 and dr_val == 0:
                    amount = cr_val
                elif dr_val > 0 and cr_val > 0:
                    amount = cr_val if cr_val > dr_val else -dr_val
            elif 'amount' in col_map and col_map['amount'] < len(row):
                raw_amt = str(row[col_map['amount']] or '')
                amount = self.clean_amount(raw_amt)
            elif 'debit' in col_map and col_map['debit'] < len(row):
                dr_val = abs(self.clean_amount(str(row[col_map['debit']] or '')))
                if dr_val > 0:
                    amount = -dr_val
            elif 'credit' in col_map and col_map['credit'] < len(row):
                cr_val = abs(self.clean_amount(str(row[col_map['credit']] or '')))
                if cr_val > 0:
                    amount = cr_val

            if amount == 0:
                return None

            return {
                'date': date,
                'description': description,
                'amount': amount,
                'balance': balance,
                'category': None,
            }
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Strategy 2: Multi-line Block Stream Collector
    # -------------------------------------------------------------------------
    def _parse_with_block_collector(self, pdf) -> List[Dict[str, Any]]:
        """
        Accumulates all lines belonging to a single transaction block
        between transaction start date markers.
        """
        extracted = []
        all_lines = []

        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split('\n'))

        # Group lines into transaction blocks
        blocks = []
        current_block = []

        for line in all_lines:
            line_str = line.strip()
            if not line_str:
                continue

            if self.DATE_PATTERN.match(line_str):
                if current_block:
                    blocks.append(current_block)
                current_block = [line_str]
            elif current_block:
                current_block.append(line_str)

        if current_block:
            blocks.append(current_block)

        for block in blocks:
            txn = self._parse_transaction_block(block)
            if txn:
                trans_key = (
                    txn['date'].isoformat(),
                    txn['description'][:60],
                    str(abs(txn['amount']))
                )
                if trans_key not in self.seen_transactions:
                    self.seen_transactions.add(trans_key)
                    extracted.append(txn)

        return extracted

    def _parse_transaction_block(self, block: List[str]) -> Optional[Dict[str, Any]]:
        """Parse a continuous multi-line block into a single transaction."""
        full_text = " ".join(block).strip()
        # Find date
        date_match = self.DATE_PATTERN.match(full_text)
        if not date_match:
            return None

        date_str = date_match.group(1)
        try:
            date = self.parse_date(date_str)
        except Exception:
            return None

        # Extract numeric amounts from the text
        amount_matches = list(re.finditer(r'([\d,]+\.\d{2})', full_text))
        if not amount_matches:
            return None

        if len(amount_matches) >= 3:
            col1 = self.clean_amount(amount_matches[-3].group(1))
            col2 = self.clean_amount(amount_matches[-2].group(1))
            balance = self.clean_amount(amount_matches[-1].group(1))

            if col1 > 0 and col2 == 0:
                amount = -col1
            elif col2 > 0 and col1 == 0:
                amount = col2
            else:
                amount = -col1 if col1 > 0 else col2

            desc_end_idx = amount_matches[-3].start()
        elif len(amount_matches) == 2:
            amt_val = self.clean_amount(amount_matches[-2].group(1))
            balance = self.clean_amount(amount_matches[-1].group(1))
            amount = -amt_val
            desc_end_idx = amount_matches[-2].start()
        else:
            amount = -self.clean_amount(amount_matches[-1].group(1))
            balance = Decimal('0.00')
            desc_end_idx = amount_matches[-1].start()

        desc_start_idx = date_match.end()
        if desc_end_idx > desc_start_idx:
            description = full_text[desc_start_idx:desc_end_idx].strip()
        else:
            # Strip date match and numeric amounts from the string
            remaining = full_text[desc_start_idx:].strip()
            for m in amount_matches:
                remaining = remaining.replace(m.group(0), '')
            description = remaining.strip()

        description = re.sub(r'[\s/|-]+$', '', description).strip()
        if not description:
            description = "Bank Transaction"

        return {
            'date': date,
            'description': description,
            'amount': amount,
            'balance': balance,
            'category': None,
        }

    # -------------------------------------------------------------------------
    # Strategy 3: Regex Line Parser (Fallback)
    # -------------------------------------------------------------------------
    def _parse_line_regex(self, line: str) -> Optional[Dict[str, Any]]:
        """Line-by-line regex parsing for standard single-line statements."""
        # Pattern 1: Date Desc Debit Credit Balance
        p1 = r'^(\d{1,2}[-/.](?:[A-Za-z]{3,9}|\d{1,2})[-/.](?:\d{4}|\d{2}))\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$'
        m1 = re.match(p1, line.strip(), re.IGNORECASE)
        if m1:
            try:
                date_str, desc, col1, col2, bal_str = m1.groups()
                date = self.parse_date(date_str)
                v1, v2 = self.clean_amount(col1), self.clean_amount(col2)
                balance = self.clean_amount(bal_str)
                amount = -v1 if v1 > 0 else v2
                return {'date': date, 'description': desc.strip(), 'amount': amount, 'balance': balance, 'category': None}
            except Exception:
                pass

        # Pattern 2: Date Desc Amount Balance
        p2 = r'^(\d{1,2}[-/.](?:[A-Za-z]{3,9}|\d{1,2})[-/.](?:\d{4}|\d{2}))\s+(.+?)\s+([-\d,]+\.\d{2})\s+([\d,]+\.\d{2})$'
        m2 = re.match(p2, line.strip(), re.IGNORECASE)
        if m2:
            try:
                date_str, desc, amt_str, bal_str = m2.groups()
                date = self.parse_date(date_str)
                amount = self.clean_amount(amt_str)
                balance = self.clean_amount(bal_str)
                return {'date': date, 'description': desc.strip(), 'amount': amount, 'balance': balance, 'category': None}
            except Exception:
                pass

        return None

    # -------------------------------------------------------------------------
    # Mathematical Balance Reconciliation
    # -------------------------------------------------------------------------
    def _reconcile_running_balances(self):
        """
        Reconcile transactions using running balance math:
        Balance[i] - Balance[i-1] == Amount[i]
        Corrects signs and detects anomalies.
        """
        if not self.transactions or len(self.transactions) < 2:
            return

        # Sort chronologically by date if needed for running balance calculation
        # But preserve original parse sequence if dates are equal
        for i in range(1, len(self.transactions)):
            prev = self.transactions[i - 1]
            curr = self.transactions[i]

            prev_bal = prev.get('balance', Decimal('0'))
            curr_bal = curr.get('balance', Decimal('0'))

            if prev_bal != Decimal('0') and curr_bal != Decimal('0'):
                expected_delta = curr_bal - prev_bal
                curr_amt = curr['amount']

                # If magnitude matches but sign was wrong
                if abs(expected_delta) == abs(curr_amt):
                    if expected_delta != curr_amt:
                        curr['amount'] = expected_delta
                elif abs(expected_delta - curr_amt) > Decimal('0.05'):
                    self.balance_errors += 1
                    logger.debug(
                        f"Balance mismatch: {prev_bal} -> {curr_bal} (delta {expected_delta}) "
                        f"vs amount {curr_amt}"
                    )

    def _is_header(self, line: str) -> bool:
        """Check if line is a header row."""
        header_keywords = [
            'transaction date', 'value date', 'narration', 'particulars',
            'debit', 'credit', 'balance', 'account number', 'opening balance',
            'closing balance', 'statement of account', 'statement period', 'page '
        ]
        line_lower = line.lower()
        if any(k in line_lower for k in ['account number', 'statement of account', 'statement period']):
            return True
        return sum(k in line_lower for k in header_keywords) >= 2

    def _validate_and_add_transaction(self, txn: Dict[str, Any]) -> bool:
        trans_key = (
            txn['date'].isoformat(),
            txn['description'][:60],
            str(abs(txn['amount']))
        )
        if trans_key in self.seen_transactions:
            return False
        self.seen_transactions.add(trans_key)
        self.transactions.append(txn)
        return True

    def get_parsing_stats(self) -> Dict[str, Any]:
        return {
            'transactions_found': len(self.transactions),
            'balance_errors': self.balance_errors,
            'strategy_used': self.strategy_used,
        }
