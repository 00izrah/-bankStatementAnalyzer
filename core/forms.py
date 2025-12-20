from django import forms
from .models import UploadedFile, Category, Transaction

class UploadStatementForm(forms.ModelForm):
    class Meta:
        model = UploadedFile
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'form-input mt-1 block w-full',
                'accept': '.pdf',
            }),
        }
        labels = {
            'file': 'Bank Statement (PDF)',
        }
        help_texts = {
            'file': 'Upload your bank statement PDF. Works with all Nigerian banks.',
        }

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'keywords']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input mt-1 block w-full'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea mt-1 block w-full', 'rows': 3}),
            'keywords': forms.Textarea(attrs={'class': 'form-textarea mt-1 block w-full', 'rows': 3}),
        }

class TransactionCategoryForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['category', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'class': 'form-textarea mt-1 block w-full', 'rows': 2}),
        }