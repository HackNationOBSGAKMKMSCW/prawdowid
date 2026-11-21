from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Prawdowid API")
api = APIRouter(prefix="/api")


class ItemCreate(BaseModel):
    name: str


class Item(ItemCreate):
    id: int


items: list[Item] = [Item(id=1, name="First item"), Item(id=2, name="Second item")]


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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


app.include_router(api)
