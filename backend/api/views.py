import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from main import search_imslp


@csrf_exempt
@require_http_methods(["POST"])
def chat_view(request):
    try:
        body = json.loads(request.body)
        prompt = body.get("prompt", "").strip()
        if not prompt:
            return JsonResponse({"error": "prompt is required"}, status=400)
        return JsonResponse({"response": prompt})
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def search_view(request):
    client_ip = request.META.get("REMOTE_ADDR")
    try:
        body = json.loads(request.body)
        query = body.get("query", "").strip()
        print(f"[search] request from {client_ip} -> query={query!r}")
        if not query:
            return JsonResponse({"error": "query is required"}, status=400)
        results = search_imslp(query)
        print(f"[search] sending {len(results)} result(s) to {client_ip}: {results}")
        return JsonResponse({"query": query, "results": results})
    except json.JSONDecodeError:
        print(f"[search] invalid JSON from {client_ip}")
        return JsonResponse({"error": "invalid JSON"}, status=400)
    except Exception as e:
        print(f"[search] error for {client_ip}: {e}")
        return JsonResponse({"error": str(e)}, status=500)
