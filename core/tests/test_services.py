"""
Unit tests for application services (AnalyticsService, AuditLogger, UploadService).
"""
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from core.models import Category, UploadedFile, Transaction
from core.services.analytics_service import AnalyticsService
from core.services.logging_service import AuditLogger


class AuditLoggerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='loggeruser', password='password123')

    def test_log_upload(self):
        log = AuditLogger.log_upload(self.user, "stmt.pdf", 1024, success=True, transaction_count=10)
        self.assertEqual(log['action'], 'file_upload')
        self.assertEqual(log['user_id'], self.user.id)
        self.assertTrue(log['success'])
        self.assertIn('timestamp', log)

    def test_log_delete(self):
        log = AuditLogger.log_delete(self.user, 1, 5)
        self.assertEqual(log['action'], 'file_delete')
        self.assertEqual(log['file_id'], 1)

    def test_log_transaction_edit(self):
        log = AuditLogger.log_transaction_edit(self.user, 42, {'old_category': 'Food', 'new_category': 'Dining'})
        self.assertEqual(log['action'], 'transaction_edit')
        self.assertEqual(log['transaction_id'], 42)


class AnalyticsServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='analyticsuser', password='password123')
        file = SimpleUploadedFile("stmt.pdf", b"%PDF-1.4 content", content_type="application/pdf")
        self.uploaded_file = UploadedFile.objects.create(
            user=self.user, file=file, original_filename="stmt.pdf", transaction_count=3
        )
        self.cat_food = Category.objects.create(name='Food', user=self.user)
        self.cat_income = Category.objects.create(name='Income', user=self.user)

        today = timezone.now().date()
        Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=today,
            description="Supermarket Food",
            amount=Decimal('-10000.00'),
            balance=Decimal('90000.00'),
            category=self.cat_food,
        )
        Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=today,
            description="Restaurant Dinner",
            amount=Decimal('-5000.00'),
            balance=Decimal('85000.00'),
            category=self.cat_food,
        )
        Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=today,
            description="Monthly Salary",
            amount=Decimal('100000.00'),
            balance=Decimal('100000.00'),
            category=self.cat_income,
        )

    def test_get_dashboard_data_stats(self):
        service = AnalyticsService(self.user)
        data = service.get_dashboard_data()

        self.assertEqual(data['stats']['total_spent'], Decimal('15000.00'))
        self.assertEqual(data['stats']['total_income'], Decimal('100000.00'))
        self.assertEqual(data['stats']['transaction_count'], 3)
        self.assertEqual(data['stats']['net_flow'], Decimal('85000.00'))

    def test_category_breakdown(self):
        service = AnalyticsService(self.user)
        data = service.get_dashboard_data()

        categories = data['categories']
        self.assertTrue(len(categories) > 0)
        food_cat = next((c for c in categories if c['category__name'] == 'Food'), None)
        self.assertIsNotNone(food_cat)
        self.assertEqual(food_cat['total'], 15000.0)

    def test_date_range_filter(self):
        # Create an old transaction from 400 days ago
        old_date = timezone.now().date() - timedelta(days=400)
        Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=old_date,
            description="Old Expense",
            amount=Decimal('-2000.00'),
            balance=Decimal('50000.00'),
        )

        service = AnalyticsService(self.user)
        # Filter for 30 days
        data_month = service.get_dashboard_data(date_filter='month')
        self.assertEqual(data_month['stats']['transaction_count'], 3)

        # All time should include old transaction
        data_all = service.get_dashboard_data(date_filter='all')
        self.assertEqual(data_all['stats']['transaction_count'], 4)
