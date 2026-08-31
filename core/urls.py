from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('upload/', views.upload_statement, name='upload'),
    path('categories/', views.manage_categories, name='manage_categories'),
    path('transaction/<int:transaction_id>/edit/', views.edit_transaction, name='edit_transaction'),
    path('statement/<int:file_id>/delete/', views.delete_statement, name='delete_statement'),
    path('clear-all/', views.clear_all_data, name='clear_all_data'),
    path('export/csv/', views.export_transactions_csv, name='export_transactions_csv'),
    path('export/json/', views.export_transactions_json, name='export_transactions_json'),
]