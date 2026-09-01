"""
Management command to re-run auto-categorization on existing transactions.

Usage:
    python manage.py recategorize_transactions
    python manage.py recategorize_transactions --ai
    python manage.py recategorize_transactions --ai --user 2
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import User
from core.models import Transaction, Category
from core.services.categorization_service import CategorizationService


class Command(BaseCommand):
    help = 'Re-categorizes existing transactions using regex rules with optional Groq AI fallback.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ai',
            action='store_true',
            help='Run AI-powered fallback categorization on remaining uncategorized / Other transactions.',
        )
        parser.add_argument(
            '--user',
            type=int,
            default=None,
            help='Recategorize only for a specific user ID.',
        )

    def handle(self, *args, **options):
        use_ai = options.get('ai', False)
        user_id = options.get('user')

        transactions = Transaction.objects.all()
        if user_id:
            transactions = transactions.filter(uploaded_file__user_id=user_id)

        categories = {
            cat.name.lower(): cat 
            for cat in Category.objects.filter(is_system=True)
        }

        self.stdout.write("Phase 1: Running fast rule-based categorization...")
        rule_updated_count = 0
        with transaction.atomic():
            for txn in transactions:
                # Load user categories if user exists
                user_cats = dict(categories)
                if txn.uploaded_file and txn.uploaded_file.user:
                    for uc in Category.objects.filter(user=txn.uploaded_file.user):
                        user_cats[uc.name.lower()] = uc

                matched_cat, detected_merchant = CategorizationService.categorize_transaction(
                    txn.description,
                    txn.amount,
                    user_cats
                )

                changed = False
                if matched_cat and txn.category != matched_cat:
                    txn.category = matched_cat
                    changed = True

                if detected_merchant and (not txn.notes or 'Merchant:' not in txn.notes):
                    txn.notes = f"Merchant: {detected_merchant}"
                    changed = True

                if changed:
                    txn.save()
                    rule_updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"  [OK] Rule-based pass: Updated {rule_updated_count} transactions."
        ))

        if use_ai:
            self.stdout.write("\nPhase 2: Running Groq AI categorization on remaining 'Other' / uncategorized...")
            users = User.objects.filter(id=user_id) if user_id else User.objects.filter(uploadedfile__isnull=False).distinct()
            total_ai_updated = 0
            for u in users:
                self.stdout.write(f"  AI Processing for user {u.username} (ID: {u.id})...")
                res = CategorizationService.bulk_ai_categorize_user_transactions(
                    user=u,
                    only_uncategorized=True,
                    max_transactions=300,
                    batch_size=30
                )
                updated = res.get('updated', 0)
                total_ai_updated += updated
                self.stdout.write(self.style.SUCCESS(
                    f"    [OK] User {u.username}: AI categorized {updated} transactions."
                ))

            self.stdout.write(self.style.SUCCESS(
                f"\nTotal AI Categorized: {total_ai_updated} transactions."
            ))

