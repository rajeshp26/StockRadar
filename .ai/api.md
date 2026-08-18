# API Conventions

## Backend (FastAPI)

### Base URL
- Local: `http://localhost:8001`
- Via Frontend Proxy: `http://localhost:9002/api/proxy/`

### Authentication
All protected endpoints require:
```
Authorization: Bearer <firebase_id_token>
```

### Response Format
```json
{
  "data": { ... },
  "error": null
}
```

### Error Responses
```json
{
  "data": null,
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found"
  }
}
```

### Pagination
```json
{
  "data": [...],
  "total": 100,
  "page": 1,
  "per_page": 20
}
```

## Endpoint Conventions

- `GET /resource` — List all
- `GET /resource/{id}` — Get one
- `POST /resource` — Create
- `PUT /resource/{id}` — Update
- `DELETE /resource/{id}` — Delete

## Pydantic Models

All request/response bodies use Pydantic v2 models:
```python
from pydantic import BaseModel, Field

class WatchlistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
```

## SSE (Server-Sent Events)

Real-time price updates use SSE via the Next.js bridge:
```
GET /api/proxy/stream/prices?tickers=AAPL,MSFT
```

Response: `text/event-stream` with JSON payloads
