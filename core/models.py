from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    keywords = models.TextField(help_text="Comma-separated keywords for automatic categorization")
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'user'],
                name='unique_category_per_user'
            )
        ]

    def __str__(self):
        return self.name

    @property
    def keyword_list(self):
        return [k.strip().lower() for k in self.keywords.split(',') if k.strip()]

class UploadedFile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='statements/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    transaction_count = models.IntegerField(default=0)

    def __str__(self):
        return f"Statement - {self.uploaded_at.strftime('%Y-%m-%d %H:%M')}"

class Transaction(models.Model):
    uploaded_file = models.ForeignKey(UploadedFile, on_delete=models.CASCADE)
    date = models.DateField()
    description = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.date} - {self.description[:30]} - ₦{self.amount}"

    class Meta:
        ordering = ['-date']