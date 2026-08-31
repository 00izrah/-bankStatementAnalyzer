"""
Spreadsheet parser for Excel (.xlsx, .xls) and CSV (.csv) bank statements.
"""
import os
import csv
import logging
import re
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from .base import BaseStatementParser

logger = logging.getLogger('bankstatements')


class SpreadsheetStatementParser(BaseStatementParser):
    """
    Parser for Excel (.xlsx, .xls) and CSV (.csv) bank statements.
    Automatically detects header rows and maps transaction columns.
    """

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.seen_transactions = set()
        self.balance_errors = 0

    def parse_page(self, text: str) -> None:
        pass

    def parse(self) -> List[Dict[str, Any]]:
        """Parse the spreadsheet file and return extracted transactions."""
        ext = os.path.splitext(self.pdf_path)[1].lower()
        if ext in ('.xlsx', '.xls'):
            rows = self._read_excel_rows()
        elif ext == '.csv':
            rows = self._read_csv_rows()
        else:
            raise ValueError(f"Unsupported spreadsheet format: {ext}")

        if not rows:
            return []

        # Find header row and column mapping
        col_map, start_row = self._find_header_and_mapping(rows)
        if not col_map or 'date' not in col_map:
            raise ValueError("Could not detect bank statement columns (Date, Description, Amount/Debit/Credit) in spreadsheet.")

        for row in rows[start_row:]:
            if not row or not any(row):
                continue

            txn = self._extract_transaction_from_row(row, col_map)
            if txn:
                trans_key = (
                    txn['date'].isoformat(),
                    txn['description'][:60],
                    str(abs(txn['amount']))
                )
                if trans_key not in self.seen_transactions:
                    self.seen_transactions.add(trans_key)
                    self.transactions.append(txn)

        self._reconcile_running_balances()
        return self.transactions

    def _read_excel_rows(self) -> List[List[Any]]:
        """Read all rows from the active sheet in the Excel workbook."""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(self.pdf_path, data_only=True)
            sheet = wb.active
            rows = []
            for row in sheet.iter_rows(values_only=True):
                rows.append([cell for cell in row])
            return rows
        except Exception as e:
            logger.error(f"Failed to read Excel workbook: {e}")
            raise

    def _read_csv_rows(self) -> List[List[Any]]:
        """Read all rows from a CSV file with automatic dialect detection."""
        rows = []
        with open(self.pdf_path, 'r', encoding='utf-8', errors='replace') as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
                reader = csv.reader(f, dialect)
            except Exception:
                reader = csv.reader(f)
            for row in reader:
                rows.append(row)
        return rows

    def _find_header_and_mapping(self, rows: List[List[Any]]) -> Tuple[Optional[Dict[str, int]], int]:
        """Scan first 30 rows to find table header row and map columns."""
        for idx, row in enumerate(rows[:30]):
            cleaned = [re.sub(r'[\r\n\s]+', ' ', str(cell or '')).strip().lower() for cell in row]
            col_map = {}
            for col_idx, h in enumerate(cleaned):
                if not h:
                    continue
                if any(k in h for k in ['trans date', 'txn date', 'tx date', 'post date', 'value date', 'date']):
                    if 'date' not in col_map or 'trans' in h or 'txn' in h:
                        col_map['date'] = col_idx
                elif any(k in h for k in ['narrat', 'particular', 'description', 'detail', 'remarks', 'memo', 'tran details', 'payee', 'beneficiary']):
                    col_map['description'] = col_idx
                elif any(k in h for k in ['debit', 'withdrawal', 'dr amount', 'dr', 'money out', 'debit (ngn)']):
                    col_map['debit'] = col_idx
                elif any(k in h for k in ['credit', 'deposit', 'cr amount', 'cr', 'money in', 'credit (ngn)']):
                    col_map['credit'] = col_idx
                elif any(k in h for k in ['balance', 'bal', 'closing balance', 'ledger balance']):
                    col_map['balance'] = col_idx
                elif 'amount' in h and 'debit' not in col_map and 'credit' not in col_map:
                    col_map['amount'] = col_idx

            has_amount = any(k in col_map for k in ['debit', 'credit', 'amount', 'balance'])
            if 'date' in col_map and has_amount:
                # If description column wasn't explicitly named, pick first unmapped string column
                if 'description' not in col_map:
                    for c_idx in range(len(row)):
                        if c_idx not in col_map.values():
                            col_map['description'] = c_idx
                            break
                return col_map, idx + 1

        return None, 0

    def _extract_transaction_from_row(self, row: List[Any], col_map: Dict[str, int]) -> Optional[Dict[str, Any]]:
        """Parse a single spreadsheet row into a transaction."""
        try:
            # 1. Parse Date
            date_cell = row[col_map['date']] if col_map['date'] < len(row) else None
            if not date_cell:
                return None

            if isinstance(date_cell, (datetime, date)):
                txn_date = date_cell if isinstance(date_cell, date) else date_cell.date()
            else:
                txn_date = self.parse_date(str(date_cell))

            # 2. Extract Narration
            desc_parts = []
            if 'description' in col_map and col_map['description'] < len(row):
                cell_val = row[col_map['description']]
                if cell_val:
                    desc_parts.append(str(cell_val).strip())

            # If description is missing/empty, gather other unmapped non-numeric cells
            if not desc_parts or not "".join(desc_parts).strip():
                for c_idx, cell in enumerate(row):
                    if c_idx not in (col_map.get('date'), col_map.get('debit'), col_map.get('credit'), col_map.get('amount'), col_map.get('balance')):
                        if cell is not None and str(cell).strip():
                            val = str(cell).strip()
                            if not re.match(r'^\d+$', val) and not re.match(r'^[\d,.-]+$', val):
                                desc_parts.append(val)

            description = re.sub(r'[\r\n\s]+', ' ', " ".join(desc_parts)).strip()
            if not description:
                description = "Bank Transaction"

            # 3. Balance
            balance = Decimal('0.00')
            if 'balance' in col_map and col_map['balance'] < len(row):
                bal_val = row[col_map['balance']]
                if bal_val is not None and str(bal_val).strip():
                    balance = self.clean_amount(str(bal_val))

            # 4. Amounts
            amount = Decimal('0.00')
            if 'debit' in col_map and 'credit' in col_map:
                dr_val = abs(self.clean_amount(str(row[col_map['debit']] or ''))) if col_map['debit'] < len(row) else Decimal('0')
                cr_val = abs(self.clean_amount(str(row[col_map['credit']] or ''))) if col_map['credit'] < len(row) else Decimal('0')

                if dr_val > 0 and cr_val == 0:
                    amount = -dr_val
                elif cr_val > 0 and dr_val == 0:
                    amount = cr_val
                elif dr_val > 0 and cr_val > 0:
                    amount = cr_val if cr_val > dr_val else -dr_val
            elif 'amount' in col_map and col_map['amount'] < len(row):
                amt_val = row[col_map['amount']]
                amount = self.clean_amount(str(amt_val or ''))
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
                'date': txn_date,
                'description': description,
                'amount': amount,
                'balance': balance,
                'category': None,
            }
        except Exception:
            return None

    def _reconcile_running_balances(self):
        """Reconcile transactions using running balance math."""
        if not self.transactions or len(self.transactions) < 2:
            return

        for i in range(1, len(self.transactions)):
            prev = self.transactions[i - 1]
            curr = self.transactions[i]

            prev_bal = prev.get('balance', Decimal('0'))
            curr_bal = curr.get('balance', Decimal('0'))

            if prev_bal != Decimal('0') and curr_bal != Decimal('0'):
                expected_delta = curr_bal - prev_bal
                curr_amt = curr['amount']
                if abs(expected_delta) == abs(curr_amt) and expected_delta != curr_amt:
                    curr['amount'] = expected_delta
                elif abs(expected_delta - curr_amt) > Decimal('0.05'):
                    self.balance_errors += 1

    def get_parsing_stats(self) -> Dict[str, Any]:
        return {
            'transactions_found': len(self.transactions),
            'balance_errors': self.balance_errors,
            'strategy_used': 'spreadsheet_parser',
        }
