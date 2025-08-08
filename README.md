"# stockapi" 

## Desenvolvimento (somente dev)
- Suba com Docker Compose: `docker compose up --build`
- Swagger: http://localhost:8000/docs
- Health: /health | Readiness: /ready
- GET exemplo: /stock/AAPL?request_date=2025-08-07
- POST exemplo: /stock/AAPL com body `{ "amount": 3 }`

## Notas importantes (dev)
- X-Trace-Id: retornado em todas respostas (incluindo erros) via middleware.
- Data padrão: se `request_date` não for informado, usa o último dia útil para evitar falhas de fim de semana/feriado.
- Cache:
  - Chave: `stock:{SYMBOL}:{YYYY-MM-DD}` com prefixo `stocks:` no Redis.
  - Invalidação em POST remove `stocks:stock:{SYMBOL}:*` apenas quando Redis está ativo. Fallback in-memory não suporta pattern delete (limitação aceitável em dev).
- Polygon:
  - Autenticação via header `Authorization: Bearer <POLYGON_API_KEY>`.
  - Erros HTTP são mapeados para `PolygonError` (unauthorized, rate_limited, http_error).
- MarketWatch:
  - Pode exigir `MARKETWATCH_COOKIE` para reduzir bloqueios.
- Logs:
  - Plain por padrão; ajuste com `LOG_FORMAT`/`LOG_UTC`. `jq` não é necessário no Windows.
