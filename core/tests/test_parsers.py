"""
Unit tests for base and universal bank statement parsers.
"""
from decimal import Decimal
from datetime import datetime
from django.test import TestCase
from core.parsers.base import BaseStatementParser
from core.parsers.universal import UniversalBankParser


class ConcreteParser(BaseStatementParser):
    def parse_page(self, text: str) -> None:
        pass


class BaseParserTest(TestCase):
    def setUp(self):
        self.parser = ConcreteParser("dummy.pdf")

    def test_clean_amount(self):
        self.assertEqual(self.parser.clean_amount("₦1,250.50"), Decimal("1250.50"))
        self.assertEqual(self.parser.clean_amount(" 50,000.00 "), Decimal("50000.00"))
        self.assertEqual(self.parser.clean_amount("-₦500.00"), Decimal("-500.00"))
        self.assertEqual(self.parser.clean_amount("(1,500.00)"), Decimal("-1500.00"))
        self.assertEqual(self.parser.clean_amount("2,000.00 CR"), Decimal("2000.00"))
        self.assertEqual(self.parser.clean_amount("3,500.00 DR"), Decimal("-3500.00"))
        self.assertEqual(self.parser.clean_amount(""), Decimal("0"))
        self.assertEqual(self.parser.clean_amount("--"), Decimal("0"))

    def test_parse_date_formats(self):
        # DD-MMM-YY (common in Nigerian bank statements)
        d1 = self.parser.parse_date("04-AUG-25")
        self.assertEqual(d1.day, 4)
        self.assertEqual(d1.month, 8)
        self.assertEqual(d1.year, 2025)

        # DD/MM/YYYY
        d2 = self.parser.parse_date("15/12/2024")
        self.assertEqual(d2.day, 15)
        self.assertEqual(d2.month, 12)
        self.assertEqual(d2.year, 2024)

        # ISO format YYYY-MM-DD
        d3 = self.parser.parse_date("2025-01-30")
        self.assertEqual(d3.day, 30)
        self.assertEqual(d3.month, 1)
        self.assertEqual(d3.year, 2025)

        # Date with timestamp attached
        d4 = self.parser.parse_date("2025-02-14 10:45:00")
        self.assertEqual(d4.day, 14)
        self.assertEqual(d4.month, 2)

    def test_parse_date_invalid(self):
        with self.assertRaises(ValueError):
            self.parser.parse_date("not-a-valid-date")


class UniversalBankParserTest(TestCase):
    def setUp(self):
        self.parser = UniversalBankParser("dummy.pdf")

    def test_header_detection(self):
        self.assertTrue(self.parser._is_header("Transaction Date Description Debit Credit Balance"))
        self.assertTrue(self.parser._is_header("Account Number: 0123456789 Statement Period"))
        self.assertFalse(self.parser._is_header("04-AUG-25 Transfer to John Doe 1,000.00 5,000.00"))

    def test_table_column_detector(self):
        headers = ['Trans Date', 'Narration / Description', 'Debit (NGN)', 'Credit (NGN)', 'Balance']
        col_map = self.parser._detect_table_columns(headers)
        self.assertIsNotNone(col_map)
        self.assertEqual(col_map['date'], 0)
        self.assertEqual(col_map['description'], 1)
        self.assertEqual(col_map['debit'], 2)
        self.assertEqual(col_map['credit'], 3)
        self.assertEqual(col_map['balance'], 4)

    def test_extract_transaction_from_table_row(self):
        headers = ['Trans Date', 'Narration', 'Debit', 'Credit', 'Balance']
        col_map = self.parser._detect_table_columns(headers)

        # Debit Row (Chowdeck)
        row_debit = ['04-AUG-2025', 'POS/WEB PURCHASE CHOWDECK LAGOS', '4,500.00', '', '95,500.00']
        txn_debit = self.parser._extract_transaction_from_table_row(row_debit, col_map)
        self.assertIsNotNone(txn_debit)
        self.assertEqual(txn_debit['amount'], Decimal('-4500.00'))
        self.assertEqual(txn_debit['balance'], Decimal('95500.00'))
        self.assertIn('CHOWDECK', txn_debit['description'])

        # Credit Row (Salary)
        row_credit = ['05-AUG-2025', 'NIP/SALARY INFLOW AUGUST 2025', '', '250,000.00', '345,500.00']
        txn_credit = self.parser._extract_transaction_from_table_row(row_credit, col_map)
        self.assertIsNotNone(txn_credit)
        self.assertEqual(txn_credit['amount'], Decimal('250000.00'))
        self.assertEqual(txn_credit['balance'], Decimal('345500.00'))

    def test_parse_transaction_block(self):
        # Multi-line statement block (3 lines)
        block = [
            "04-AUG-25 NIP/OPAY/0901234567/JOHN DOE",
            "REF: 998877665544 PAYMENT FOR RENT",
            "150,000.00 0.00 500,000.00"
        ]
        txn = self.parser._parse_transaction_block(block)
        self.assertIsNotNone(txn)
        self.assertEqual(txn['amount'], Decimal('-150000.00'))
        self.assertEqual(txn['balance'], Decimal('500000.00'))
        self.assertIn("PAYMENT FOR RENT", txn['description'])

    def test_reconcile_running_balances(self):
        # Balance delta resolves sign ambiguity
        self.parser.transactions = [
            {
                'date': datetime(2025, 8, 1),
                'description': 'Opening Transaction',
                'amount': Decimal('10000.00'),
                'balance': Decimal('100000.00'),
            },
            {
                'date': datetime(2025, 8, 2),
                'description': 'Ambiguous Transaction (Balance went down by 20k)',
                'amount': Decimal('20000.00'),  # Incorrectly recorded as positive
                'balance': Decimal('80000.00'),  # 100k - 80k = -20k
            }
        ]
        self.parser._reconcile_running_balances()
        self.assertEqual(self.parser.transactions[1]['amount'], Decimal('-20000.00'))


class SpreadsheetParserTest(TestCase):
    def test_csv_parsing(self):
        import tempfile
        import os
        from core.parsers.spreadsheet import SpreadsheetStatementParser
        from core.parsers import get_parser_for_file

        csv_content = (
            "Account Statement\n"
            "Period: Aug 2025\n"
            "Date,Narration,Debit,Credit,Balance\n"
            "01-Aug-2025,Salary Inflow,,300000.00,300000.00\n"
            "02-Aug-2025,Chowdeck Lagos,5000.00,,295000.00\n"
            "03-Aug-2025,IKEDC Electricity Token,10000.00,,285000.00\n"
        )
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.csv') as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            parser_cls = get_parser_for_file(temp_path)
            self.assertEqual(parser_cls, SpreadsheetStatementParser)

            parser = parser_cls(temp_path)
            txns = parser.parse()
            self.assertEqual(len(txns), 3)

            self.assertEqual(txns[0]['amount'], Decimal('300000.00'))
            self.assertEqual(txns[0]['description'], 'Salary Inflow')

            self.assertEqual(txns[1]['amount'], Decimal('-5000.00'))
            self.assertEqual(txns[1]['description'], 'Chowdeck Lagos')

            self.assertEqual(txns[2]['amount'], Decimal('-10000.00'))
            self.assertEqual(txns[2]['description'], 'IKEDC Electricity Token')
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_excel_parsing(self):
        import tempfile
        import os
        import openpyxl
        from core.parsers.spreadsheet import SpreadsheetStatementParser

        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as f:
            temp_path = f.name

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Statement"
            ws.append(["Bank Account Statement - GTBank"])
            ws.append(["Trans Date", "Description / Narration", "Debit", "Credit", "Balance"])
            ws.append(["2025-08-10", "Transfer to Cowrywise", "20000.00", "", "180000.00"])
            ws.append(["2025-08-11", "MTN Airtime VTU", "2000.00", "", "178000.00"])
            wb.save(temp_path)

            parser = SpreadsheetStatementParser(temp_path)
            txns = parser.parse()
            self.assertEqual(len(txns), 2)
            self.assertEqual(txns[0]['amount'], Decimal('-20000.00'))
            self.assertIn("Cowrywise", txns[0]['description'])
            self.assertEqual(txns[1]['amount'], Decimal('-2000.00'))
            self.assertIn("MTN Airtime", txns[1]['description'])
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
