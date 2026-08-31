"""
Management command to re-run auto-categorization on existing transactions.
"""
from django.core.management.base import BaseCommand
from django.db import transaction, models
from core.models import Transaction, Category
from core.services.categorization_service import CategorizationService


class Command(BaseCommand):
    help = 'Re-categorizes all existing transactions using the enhanced Nigerian categorization engine'

    def handle(self, *args, **options):
        transactions = Transaction.objects.all()
        categories = {
            cat.name.lower(): cat 
            for cat in Category.objects.filter(is_system=True)
        }

        updated_count = 0
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
                    updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully updated categorization for {updated_count} of {transactions.count()} transactions."
        ))
