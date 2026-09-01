"""
API views for the AI Copilot and Semantic Search endpoints.

These views expose JSON endpoints consumed by the frontend copilot drawer.
"""
import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie

from .models import ChatMessage, Transaction
from .services.copilot_service import CopilotService
from .services.vector_store import VectorStoreService
from .services.categorization_service import CategorizationService
from .services.logging_service import logger


def check_user_rate_limit(user_id: int, action: str, limit: int, period: int = 60) -> bool:
    """
    Check if a user has exceeded the allowed number of requests in the given period (in seconds).
    Returns True if allowed, False if rate limited.
    """
    key = f"rate_limit_{action}_user_{user_id}"
    current_count = cache.get(key, 0)
    if current_count >= limit:
        return False

    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=period)
    return True


@login_required
@require_POST
def copilot_chat(request):
    """
    POST /api/copilot/chat/
    
    Body (JSON):
        {
            "message": "How much did I spend on food last month?",
            "session_id": "default"  // optional
        }
    
    Returns:
        {
            "answer": "Based on your transactions...",
            "sources": [...],
            "tool_calls_made": [...]
        }
    """
    # Check rate limit per user
    chat_limit = getattr(settings, 'AI_RATE_LIMIT_CHAT_PER_MIN', 15)
    if not check_user_rate_limit(request.user.id, "copilot_chat", chat_limit, 60):
        return JsonResponse({
            "error": "You are sending messages too quickly. Please wait a few seconds before asking another question.",
            "answer": "⚠️ AI request rate limit reached. Please wait a moment before sending another message."
        }, status=429)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    user_message = body.get("message", "").strip()
    session_id = body.get("session_id", "default")

    if not user_message:
        return JsonResponse({"error": "Message cannot be empty."}, status=400)

    # Load conversation history for this session
    history_qs = ChatMessage.objects.filter(
        user=request.user,
        session_id=session_id,
    ).order_by('created_at')

    chat_history = [
        {"role": msg.role, "content": msg.content}
        for msg in history_qs
    ]

    # Save user message
    ChatMessage.objects.create(
        user=request.user,
        session_id=session_id,
        role='user',
        content=user_message,
    )

    # Generate AI response
    copilot = CopilotService(request.user)
    result = copilot.chat(user_message, chat_history)

    # Save assistant response
    ChatMessage.objects.create(
        user=request.user,
        session_id=session_id,
        role='assistant',
        content=result['answer'],
        metadata={
            "sources": result.get('sources', []),
            "tool_calls": result.get('tool_calls_made', []),
        },
    )

    return JsonResponse(result)


@login_required
@require_POST
def copilot_clear(request):
    """
    POST /api/copilot/clear/
    
    Body (JSON):
        {"session_id": "default"}  // optional
    
    Clears conversation history for the given session.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    session_id = body.get("session_id", "default")

    deleted_count, _ = ChatMessage.objects.filter(
        user=request.user,
        session_id=session_id,
    ).delete()

    return JsonResponse({
        "status": "cleared",
        "messages_deleted": deleted_count,
    })


@login_required
@require_GET
def copilot_history(request):
    """
    GET /api/copilot/history/?session_id=default
    
    Returns conversation history for the given session.
    """
    session_id = request.GET.get("session_id", "default")

    messages = ChatMessage.objects.filter(
        user=request.user,
        session_id=session_id,
    ).order_by('created_at').values(
        'role', 'content', 'created_at'
    )

    return JsonResponse({
        "messages": [
            {
                "role": msg['role'],
                "content": msg['content'],
                "timestamp": msg['created_at'].isoformat(),
            }
            for msg in messages
        ]
    })


@login_required
@require_GET
def semantic_search(request):
    """
    GET /api/search/semantic/?q=groceries&top_k=5
    
    Performs semantic similarity search over the user's transactions.
    Falls back to text search if the vector index is empty.
    """
    query = request.GET.get("q", "").strip()
    top_k = min(int(request.GET.get("top_k", "5")), 20)
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if not query:
        return JsonResponse({"error": "Query parameter 'q' is required."}, status=400)

    store = VectorStoreService(request.user)
    results = store.search(
        query=query,
        top_k=top_k,
        date_from=date_from,
        date_to=date_to,
    )

    # Fallback to ORM text search if vector index is empty
    if not results:
        qs = Transaction.objects.filter(
            uploaded_file__user=request.user,
            description__icontains=query,
        ).select_related('category')

        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        results = [
            {
                "transaction_id": t.id,
                "date": str(t.date),
                "description": t.description[:200],
                "amount": str(t.amount),
                "category": t.category.name if t.category else "Uncategorized",
                "score": 0.0,
            }
            for t in qs[:top_k]
        ]

    return JsonResponse({"query": query, "results": results})


@login_required
@require_GET
@ensure_csrf_cookie
def copilot_status(request):
    """
    GET /api/copilot/status/
    
    Returns whether the copilot is properly configured and ready.
    """
    from django.conf import settings

    has_api_key = bool(settings.GROQ_API_KEY)
    txn_count = Transaction.objects.filter(
        uploaded_file__user=request.user
    ).count()

    # Check vector index
    try:
        store = VectorStoreService(request.user)
        index_stats = store.get_index_stats()
    except Exception:
        index_stats = {"total_vectors": 0, "index_exists": False}

    return JsonResponse({
        "ready": has_api_key and txn_count > 0,
        "has_api_key": has_api_key,
        "transaction_count": txn_count,
        "vector_index": index_stats,
    })


@login_required
@require_GET
def copilot_dashboard_summary(request):
    """
    GET /api/copilot/dashboard-summary/?date_range=all&force_refresh=false
    
    Generates or retrieves cached AI executive summary, main concerns,
    and financial improvement tips for the dashboard card.
    """
    date_filter = request.GET.get('date_range', 'all')
    force_refresh = request.GET.get('force_refresh', 'false').lower() == 'true'

    copilot = CopilotService(request.user)
    summary_data = copilot.generate_dashboard_ai_summary(
        date_filter=date_filter,
        force_refresh=force_refresh,
    )
    return JsonResponse(summary_data)


@login_required
@require_POST
def ai_auto_categorize(request):
    """
    POST /api/categories/ai-categorize/
    
    Runs LLM categorization fallback on the user's uncategorized transactions.
    Body (JSON, optional):
        {
            "only_uncategorized": true,
            "max_transactions": 100
        }
    """
    batch_limit = getattr(settings, 'AI_RATE_LIMIT_BATCH_PER_MIN', 5)
    if not check_user_rate_limit(request.user.id, "ai_auto_categorize", batch_limit, 60):
        return JsonResponse({
            "error": "AI categorization was triggered recently. Please wait a moment before running it again."
        }, status=429)

    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        body = {}

    only_uncategorized = body.get("only_uncategorized", True)
    max_txns = min(int(body.get("max_transactions", 100)), 300)

    result = CategorizationService.bulk_ai_categorize_user_transactions(
        user=request.user,
        only_uncategorized=only_uncategorized,
        max_transactions=max_txns,
        batch_size=30,
    )

    # If any transactions were updated, refresh vector index for accuracy
    if result.get('updated', 0) > 0:
        try:
            store = VectorStoreService(request.user)
            txns = Transaction.objects.filter(uploaded_file__user=request.user)
            store.index_transactions(txns)
        except Exception as e:
            logger.warning(f"Failed to update vector index after AI categorization: {e}")

    return JsonResponse(result)
