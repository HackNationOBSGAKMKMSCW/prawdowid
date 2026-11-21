from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import llm
from check import router as check_router

MAX_BODY_BYTES = 64 * 1024

app = FastAPI(title="Prawdowid API")
api = APIRouter(prefix="/api")


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return _error(413, "payload_too_large", "Zgłoszenie jest za duże.")
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return _error(422, "invalid_input", "Nie udało się przyjąć zgłoszenia.", details)


_ERROR_CODES = {404: "not_found", 405: "method_not_allowed", 429: "rate_limited"}


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    response = _error(exc.status_code, _ERROR_CODES.get(exc.status_code, "http_error"), exc.detail)
    for name, value in (exc.headers or {}).items():
        response.headers[name] = value
    return response


def _error(status: int, code: str, message_pl: str, details: list | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message_pl": message_pl, "details": details or []}}
    return JSONResponse(status_code=status, content=body)


class ItemCreate(BaseModel):
    name: str


class Item(ItemCreate):
    id: int


items: list[Item] = [Item(id=1, name="First item"), Item(id=2, name="Second item")]


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.get("/llm/health")
def llm_health() -> dict:
    return llm.health()


@api.get("/items")
def list_items() -> list[Item]:
    return items


@api.get("/items/{item_id}")
def get_item(item_id: int) -> Item:
    for item in items:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")


@api.post("/items", status_code=201)
def create_item(payload: ItemCreate) -> Item:
    item = Item(id=max((i.id for i in items), default=0) + 1, name=payload.name)
    items.append(item)
    return item


@api.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int) -> None:
    for i, item in enumerate(items):
        if item.id == item_id:
            del items[i]
            return
    raise HTTPException(status_code=404, detail="Item not found")


@api.delete("/test/{item_id}", status_code=200)
def test(element: int) -> int:
    return element


api.include_router(check_router)
app.include_router(api)
