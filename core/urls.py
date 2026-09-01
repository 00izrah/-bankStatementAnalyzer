from django.urls import path
from . import views
from . import api_views

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

    # AI Copilot & Semantic Search API
    path('api/copilot/chat/', api_views.copilot_chat, name='copilot_chat'),
    path('api/copilot/clear/', api_views.copilot_clear, name='copilot_clear'),
    path('api/copilot/history/', api_views.copilot_history, name='copilot_history'),
    path('api/copilot/status/', api_views.copilot_status, name='copilot_status'),
    path('api/copilot/dashboard-summary/', api_views.copilot_dashboard_summary, name='copilot_dashboard_summary'),
    path('api/categories/ai-categorize/', api_views.ai_auto_categorize, name='ai_auto_categorize'),
    path('api/search/semantic/', api_views.semantic_search, name='semantic_search'),
]