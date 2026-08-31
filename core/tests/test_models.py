"""
Unit tests for core models (Category, UploadedFile, Transaction).
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.utils import timezone
from core.models import Category, UploadedFile, Transaction, calculate_file_hash


class CategoryModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')

    def test_category_creation_and_str(self):
        cat = Category.objects.create(name='Groceries', user=self.user, keywords='spar, shoprite')
        self.assertEqual(str(cat), 'Groceries')
        self.assertEqual(cat.keyword_list, ['spar', 'shoprite'])

    def test_category_empty_keywords(self):
        cat = Category.objects.create(name='Other', user=self.user, keywords='')
        self.assertEqual(cat.keyword_list, [])

    def test_unique_category_per_user_constraint(self):
        Category.objects.create(name='Food', user=self.user)
        with self.assertRaises(IntegrityError):
            Category.objects.create(name='Food', user=self.user)


class UploadedFileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')

    def test_calculate_file_hash(self):
        content = b"%PDF-1.4 test bank statement data"
        file = SimpleUploadedFile("statement.pdf", content, content_type="application/pdf")
        h1 = calculate_file_hash(file)
        self.assertIsInstance(h1, str)
        self.assertEqual(len(h1), 64)

        # Re-running on same content produces deterministic hash
        file.seek(0)
        h2 = calculate_file_hash(file)
        self.assertEqual(h1, h2)

    def test_uploaded_file_creation_and_str(self):
        content = b"%PDF-1.4 sample content"
        file = SimpleUploadedFile("statement.pdf", content, content_type="application/pdf")
        uploaded = UploadedFile.objects.create(
            user=self.user,
            file=file,
            original_filename="statement.pdf",
            file_size=len(content),
        )
        self.assertTrue(str(uploaded).startswith("Statement - "))


class TransactionModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        file = SimpleUploadedFile("stmt.pdf", b"%PDF-1.4 data", content_type="application/pdf")
        self.uploaded_file = UploadedFile.objects.create(
            user=self.user, file=file, original_filename="stmt.pdf"
        )
        self.category = Category.objects.create(name='Transport', user=self.user)

    def test_transaction_creation_and_hash_auto_generation(self):
        txn = Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=timezone.now().date(),
            description="Uber Trip Lagos",
            amount=Decimal('-3500.00'),
            balance=Decimal('45000.00'),
            category=self.category,
        )
        self.assertTrue(bool(txn.content_hash))
        self.assertEqual(len(txn.content_hash), 64)
        self.assertIn("Uber Trip Lagos", str(txn))

    def test_unique_transaction_per_file_constraint(self):
        today = timezone.now().date()
        Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=today,
            description="POS purchase",
            amount=Decimal('-1500.00'),
            balance=Decimal('20000.00'),
        )
        with self.assertRaises(IntegrityError):
            Transaction.objects.create(
                uploaded_file=self.uploaded_file,
                date=today,
                description="POS purchase",
                amount=Decimal('-1500.00'),
                balance=Decimal('20000.00'),
            )
