"""
Management command to rebuild vector indexes for all users.

Usage:
    python manage.py rebuild_vector_index          # All users
    python manage.py rebuild_vector_index --user 1  # Specific user
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from core.models import Transaction
from core.services.vector_store import VectorStoreService


class Command(BaseCommand):
    help = 'Rebuild FAISS vector indexes for semantic search over transactions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=int,
            default=None,
            help='Rebuild index only for a specific user ID.',
        )

    def handle(self, *args, **options):
        user_id = options.get('user')

        if user_id:
            users = User.objects.filter(id=user_id)
            if not users.exists():
                self.stderr.write(self.style.ERROR(f'User {user_id} not found.'))
                return
        else:
            # Only users who have uploaded statements
            users = User.objects.filter(
                uploadedfile__isnull=False
            ).distinct()

        total_indexed = 0

        for user in users:
            txn_count = Transaction.objects.filter(
                uploaded_file__user=user
            ).count()

            if txn_count == 0:
                self.stdout.write(f'  Skipping user {user.username} (no transactions)')
                continue

            self.stdout.write(
                f'  Indexing {txn_count} transactions for user '
                f'{user.username} (ID: {user.id})...'
            )

            store = VectorStoreService(user)
            transactions = Transaction.objects.filter(
                uploaded_file__user=user
            )
            indexed = store.index_transactions(transactions)
            total_indexed += indexed

            self.stdout.write(
                self.style.SUCCESS(f'    [OK] Indexed {indexed} transactions')
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone! Total: {total_indexed} transactions indexed '
                f'across {users.count()} user(s).'
            )
        )
