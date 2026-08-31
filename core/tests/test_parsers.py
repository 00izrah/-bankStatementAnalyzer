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

    def test_debit_keyword_detection(self):
        self.assertTrue(self.parser._is_likely_debit("POS purchase at supermarket"))
        self.assertTrue(self.parser._is_likely_debit("USSD withdrawal fee"))
        self.assertFalse(self.parser._is_likely_debit("Salary payment from company"))

    def test_parse_amount_credit_and_debit(self):
        # Outgoing debit
        debit = self.parser._parse_amount("5,000.00", "POS Purchase at Shoprite")
        self.assertEqual(debit, Decimal("-5000.00"))

        # Explicit credit
        credit = self.parser._parse_amount("250,000.00", "Monthly Salary Inflow")
        self.assertEqual(credit, Decimal("250000.00"))

    def test_columnar_parsing(self):
        line = "04-AUG-25 Monthly Rent Payment 150,000.00 0.00 500,000.00"
        tx = self.parser._parse_columnar(line)
        self.assertIsNotNone(tx)
        self.assertEqual(tx['amount'], Decimal("-150000.00"))
        self.assertEqual(tx['balance'], Decimal("500000.00"))
        self.assertIn("Monthly Rent Payment", tx['description'])
