"""
Unit tests for application services (AnalyticsService, AuditLogger, UploadService, CategorizationService).
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
from core.services.categorization_service import CategorizationService


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


class CategorizationServiceTest(TestCase):
    def setUp(self):
        self.cat_food = Category.objects.create(name='Food & Dining', keywords='chowdeck,kfc,restaurant', is_system=True)
        self.cat_charges = Category.objects.create(name='Bank Charges & Fees', keywords='emtl,stamp duty,sms alert', is_system=True)
        self.cat_transport = Category.objects.create(name='Transportation', keywords='uber,bolt,fuel', is_system=True)
        self.cat_income = Category.objects.create(name='Income', keywords='salary,inflow', is_system=True)
        self.categories = {
            'food & dining': self.cat_food,
            'bank charges & fees': self.cat_charges,
            'transportation': self.cat_transport,
            'income': self.cat_income,
        }

    def test_clean_narration(self):
        raw = "NIP/OPAY/0901234567/REF:1234567890/CHOWDECK FAST FOOD LAGOS NG"
        cleaned = CategorizationService.clean_narration(raw)
        self.assertNotIn("NIP", cleaned)
        self.assertNotIn("REF:1234567890", cleaned)
        self.assertIn("CHOWDECK", cleaned)

    def test_extract_merchant(self):
        self.assertEqual(
            CategorizationService.extract_merchant("POS PURCHASE 12345 CHOWDECK LEKKI"),
            "Chowdeck"
        )
        self.assertEqual(
            CategorizationService.extract_merchant("TRF/UBER TRIP AMSTERDAM BV"),
            "Uber"
        )
        self.assertEqual(
            CategorizationService.extract_merchant("ELECTRONIC MONEY TRANSFER LEVY EMTL"),
            "Federal EMTL Levy"
        )

    def test_categorize_bank_charges(self):
        cat, merchant = CategorizationService.categorize_transaction(
            "ELECTRONIC MONEY TRANSFER LEVY",
            Decimal("-50.00"),
            self.categories
        )
        self.assertEqual(cat, self.cat_charges)
        self.assertEqual(merchant, "Federal EMTL Levy")

    def test_categorize_inflow_vs_outflow(self):
        # Salary Inflow
        cat_in, _ = CategorizationService.categorize_transaction(
            "MONTHLY SALARY INFLOW AUGUST",
            Decimal("350000.00"),
            self.categories
        )
        self.assertEqual(cat_in, self.cat_income)

        # Ride-hailing debit
        cat_out, merchant = CategorizationService.categorize_transaction(
            "WEB PURCHASE BOLT.EU TAXIFY",
            Decimal("-3200.00"),
            self.categories
        )
        self.assertEqual(cat_out, self.cat_transport)
        self.assertEqual(merchant, "Bolt")

    def test_parse_json_from_llm(self):
        # 1. Standard markdown codeblock JSON
        s1 = '```json\n[{"id": 1, "category_name": "Food & Dining", "clean_merchant": "Chowdeck"}]\n```'
        p1 = CategorizationService._parse_json_from_llm(s1)
        self.assertEqual(len(p1), 1)
        self.assertEqual(p1[0]['category_name'], 'Food & Dining')

        # 2. Qwen reasoning think tag wrapper
        s2 = '<think>I need to categorize this</think>\n{"results": [{"id": 2, "category_name": "Transportation", "clean_merchant": "Uber"}]}'
        p2 = CategorizationService._parse_json_from_llm(s2)
        self.assertEqual(len(p2), 1)
        self.assertEqual(p2[0]['category_name'], 'Transportation')

        # 3. Multiple JSON objects
        s3 = '{"id": 3, "category_name": "Utilities"}\n{"id": 4, "category_name": "Shopping"}'
        p3 = CategorizationService._parse_json_from_llm(s3)
        self.assertEqual(len(p3), 2)

    def test_bulk_ai_categorize_user_transactions_no_uncategorized(self):
        user = User.objects.create_user(username='aiuser', password='password123')
        res = CategorizationService.bulk_ai_categorize_user_transactions(user=user)
        self.assertEqual(res['processed'], 0)
        self.assertEqual(res['updated'], 0)


class AnalyticsServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='analyticsuser', password='password123')
        file = SimpleUploadedFile("stmt.pdf", b"%PDF-1.4 content", content_type="application/pdf")
        self.uploaded_file = UploadedFile.objects.create(
            user=self.user, file=file, original_filename="stmt.pdf", transaction_count=4
        )
        self.cat_food = Category.objects.create(name='Food & Dining', user=self.user)
        self.cat_charges = Category.objects.create(name='Bank Charges & Fees', user=self.user)
        self.cat_income = Category.objects.create(name='Income', user=self.user)

        today = timezone.now().date()
        Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=today,
            description="Supermarket Food",
            amount=Decimal('-10000.00'),
            balance=Decimal('90000.00'),
            category=self.cat_food,
            notes="Merchant: Supermarket"
        )
        Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=today,
            description="Chowdeck Food",
            amount=Decimal('-5000.00'),
            balance=Decimal('85000.00'),
            category=self.cat_food,
            notes="Merchant: Chowdeck"
        )
        Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=today,
            description="Electronic Money Transfer Levy",
            amount=Decimal('-50.00'),
            balance=Decimal('84950.00'),
            category=self.cat_charges,
            notes="Merchant: Federal EMTL Levy"
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

        self.assertEqual(data['stats']['total_spent'], Decimal('15050.00'))
        self.assertEqual(data['stats']['bank_charges_total'], Decimal('50.00'))
        self.assertEqual(data['stats']['real_spending'], Decimal('15000.00'))
        self.assertEqual(data['stats']['total_income'], Decimal('100000.00'))
        self.assertEqual(data['stats']['transaction_count'], 4)

    def test_top_merchants(self):
        service = AnalyticsService(self.user)
        data = service.get_dashboard_data()
        merchants = data['top_merchants']
        self.assertTrue(len(merchants) > 0)
        merchant_names = [m['name'] for m in merchants]
        self.assertIn("Supermarket", merchant_names)
        self.assertIn("Chowdeck", merchant_names)

    def test_category_breakdown(self):
        service = AnalyticsService(self.user)
        data = service.get_dashboard_data()

        categories = data['categories']
        self.assertTrue(len(categories) > 0)
        food_cat = next((c for c in categories if c['category__name'] == 'Food & Dining'), None)
        self.assertIsNotNone(food_cat)
        self.assertEqual(food_cat['total'], 15000.0)

    def test_search_and_category_filter(self):
        service = AnalyticsService(self.user)
        data_search = service.get_dashboard_data(search_query='Chowdeck')
        self.assertEqual(data_search['transactions'].paginator.count, 1)

        data_cat = service.get_dashboard_data(category_filter=str(self.cat_food.id))
        self.assertEqual(data_cat['transactions'].paginator.count, 2)

    def test_financial_insights(self):
        service = AnalyticsService(self.user)
        data = service.get_dashboard_data()
        insights = data['insights']

        self.assertIsNotNone(insights)
        self.assertEqual(insights['health_status'], 'Excellent')
        self.assertEqual(insights['health_color'], 'emerald')
        self.assertTrue(insights['savings_rate'] > 80.0)
        self.assertTrue(insights['daily_burn_rate'] > 0.0)
        self.assertIn(insights['peak_day_name'], ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])


class ExportServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='exportuser', password='password123')
        file = SimpleUploadedFile("stmt.pdf", b"%PDF-1.4 data", content_type="application/pdf")
        self.uploaded_file = UploadedFile.objects.create(user=self.user, file=file, original_filename="stmt.pdf")
        self.cat = Category.objects.create(name='Food & Dining', user=self.user)
        Transaction.objects.create(
            uploaded_file=self.uploaded_file,
            date=timezone.now().date(),
            description="POS Purchase Chowdeck",
            amount=Decimal('-4500.00'),
            balance=Decimal('25000.00'),
            category=self.cat,
            notes='Merchant: Chowdeck',
        )

    def test_export_csv(self):
        from core.services.export_service import ExportService
        txns = Transaction.objects.filter(uploaded_file__user=self.user)
        response = ExportService.export_csv(txns)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        content = response.content.decode('utf-8')
        self.assertIn('Date,Description,Amount (NGN),Balance (NGN)', content)
        self.assertIn('Chowdeck', content)
        self.assertIn('-4500.00', content)

    def test_export_json(self):
        from core.services.export_service import ExportService
        import json
        txns = Transaction.objects.filter(uploaded_file__user=self.user)
        response = ExportService.export_json(txns)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['description'], 'POS Purchase Chowdeck')
        self.assertEqual(data[0]['amount'], -4500.0)
