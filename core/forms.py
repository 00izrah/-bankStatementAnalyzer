from django import forms
from django.db import models
from .models import UploadedFile, Category, Transaction
from .validators import validate_uploaded_file, FileValidationError


class UploadStatementForm(forms.ModelForm):
    class Meta:
        model = UploadedFile
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'form-input mt-1 block w-full',
                'accept': '.pdf,.xlsx,.xls,.csv',
            }),
        }
        labels = {
            'file': 'Bank Statement (PDF, Excel, or CSV)',
        }
        help_texts = {
            'file': 'Upload your statement in PDF, Excel (.xlsx, .xls), or CSV format (max 10MB). Works with all Nigerian banks.',
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            try:
                validate_uploaded_file(file)
            except FileValidationError as e:
                if isinstance(e.message, list):
                    raise forms.ValidationError(e.message)
                raise forms.ValidationError(str(e.message))
        return file


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'keywords']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input mt-1 block w-full',
                'placeholder': 'Category name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea mt-1 block w-full', 
                'rows': 3,
                'placeholder': 'Optional description'
            }),
            'keywords': forms.Textarea(attrs={
                'class': 'form-textarea mt-1 block w-full', 
                'rows': 3,
                'placeholder': 'restaurant, food, dining (comma-separated)'
            }),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            name = name.strip()
            if len(name) < 2:
                raise forms.ValidationError('Category name must be at least 2 characters.')
        return name


class TransactionCategoryForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['category', 'notes']
        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-select mt-1 block w-full'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea mt-1 block w-full', 
                'rows': 3,
                'placeholder': 'Add notes about this transaction...'
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['category'].queryset = Category.objects.filter(
                models.Q(user=user) | models.Q(is_system=True)
            ).order_by('name')