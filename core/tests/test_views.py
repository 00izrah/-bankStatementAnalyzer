"""
Integration tests for core application views.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from core.models import UploadedFile, Transaction, Category


class CoreViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='viewuser', password='password123')
        self.other_user = User.objects.create_user(username='otheruser', password='password123')

    def test_home_unauthenticated(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/home.html')

    def test_home_authenticated_redirects_to_dashboard(self):
        self.client.login(username='viewuser', password='password123')
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_dashboard_login_required(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_dashboard_renders_for_logged_in_user(self):
        self.client.login(username='viewuser', password='password123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/dashboard.html')

    def test_manage_categories_get_and_post(self):
        self.client.login(username='viewuser', password='password123')
        # GET
        get_res = self.client.get(reverse('manage_categories'))
        self.assertEqual(get_res.status_code, 200)
        self.assertTemplateUsed(get_res, 'core/manage_categories.html')

        # POST
        post_res = self.client.post(reverse('manage_categories'), {
            'name': 'Investment',
            'description': 'Stocks and real estate',
            'keywords': 'crypto, shares, dividend',
        })
        self.assertRedirects(post_res, reverse('manage_categories'))
        self.assertTrue(Category.objects.filter(name='Investment', user=self.user).exists())

    def test_edit_transaction(self):
        self.client.login(username='viewuser', password='password123')
        file = SimpleUploadedFile("s.pdf", b"%PDF-1.4 content", content_type="application/pdf")
        uploaded = UploadedFile.objects.create(user=self.user, file=file, original_filename="s.pdf")
        cat = Category.objects.create(name='Tech', user=self.user)
        txn = Transaction.objects.create(
            uploaded_file=uploaded,
            date=timezone.now().date(),
            description="GitHub Subscription",
            amount=Decimal('-10.00'),
            balance=Decimal('500.00'),
        )

        edit_url = reverse('edit_transaction', kwargs={'transaction_id': txn.id})
        res = self.client.post(edit_url, {
            'category': cat.id,
            'notes': 'Monthly developer tools',
        })
        self.assertRedirects(res, reverse('dashboard'))
        txn.refresh_from_db()
        self.assertEqual(txn.category, cat)
        self.assertEqual(txn.notes, 'Monthly developer tools')

    def test_delete_statement_requires_post(self):
        self.client.login(username='viewuser', password='password123')
        file = SimpleUploadedFile("s.pdf", b"%PDF-1.4 data", content_type="application/pdf")
        uploaded = UploadedFile.objects.create(user=self.user, file=file, original_filename="s.pdf")

        delete_url = reverse('delete_statement', kwargs={'file_id': uploaded.id})
        # GET should be rejected with 405 Method Not Allowed
        get_res = self.client.get(delete_url)
        self.assertEqual(get_res.status_code, 405)

        # POST should succeed
        post_res = self.client.post(delete_url)
        self.assertRedirects(post_res, reverse('dashboard'))
        self.assertFalse(UploadedFile.objects.filter(id=uploaded.id).exists())

    def test_clear_all_data_requires_post(self):
        self.client.login(username='viewuser', password='password123')
        # GET should be rejected with 405
        get_res = self.client.get(reverse('clear_all_data'))
        self.assertEqual(get_res.status_code, 405)

        # POST should succeed
        post_res = self.client.post(reverse('clear_all_data'))
        self.assertRedirects(post_res, reverse('dashboard'))

    def test_export_csv_view(self):
        self.client.login(username='viewuser', password='password123')
        res = self.client.get(reverse('export_transactions_csv'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'text/csv; charset=utf-8')

    def test_export_json_view(self):
        self.client.login(username='viewuser', password='password123')
        res = self.client.get(reverse('export_transactions_json'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/json')

    def test_password_reset_view_renders(self):
        res = self.client.get(reverse('password_reset'))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'registration/password_reset_form.html')

