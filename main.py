import os
from typing import List, Optional, Any, Dict
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User as UserSchema, Product as ProductSchema, Address as AddressSchema, CartItem as CartItemSchema, Order as OrderSchema


app = FastAPI(title="VegHolic API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------ Helpers -------------
class ObjectIdEncoder:
    @staticmethod
    def encode(doc: Any) -> Any:
        if isinstance(doc, list):
            return [ObjectIdEncoder.encode(d) for d in doc]
        if isinstance(doc, dict):
            out: Dict[str, Any] = {}
            for k, v in doc.items():
                if isinstance(v, ObjectId):
                    out[k] = str(v)
                elif isinstance(v, list) or isinstance(v, dict):
                    out[k] = ObjectIdEncoder.encode(v)
                else:
                    out[k] = v
            return out
        if isinstance(doc, ObjectId):
            return str(doc)
        return doc


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")


# ------------ Request/Response Models -------------
class OTPRequest(BaseModel):
    phone: str


class OTPVerify(BaseModel):
    phone: str
    otp: str
    name: Optional[str] = None


class AddToCartRequest(BaseModel):
    user_id: str
    product_id: str
    variant: str = "1kg"
    qty: int = 1


class UpdateCartQty(BaseModel):
    qty: int


class AddressCreate(AddressSchema):
    pass


class CreateOrderRequest(BaseModel):
    user_id: str
    address_id: str
    payment_method: str


# ------------ Seed Data -------------
SAMPLE_PRODUCTS = [
    {
        "name": "Spinach",
        "description": "Fresh leafy spinach, rich in iron.",
        "price_per_kg": 80.0,
        "category": "leafy",
        "image_url": "https://images.unsplash.com/photo-1604909052743-94e838986d24?q=80&w=800&auto=format&fit=crop",
    },
    {
        "name": "Carrot",
        "description": "Crunchy sweet carrots.",
        "price_per_kg": 60.0,
        "category": "root",
        "image_url": "https://images.unsplash.com/photo-1547514701-42782101795e?q=80&w=800&auto=format&fit=crop",
    },
    {
        "name": "Tomato",
        "description": "Juicy farm tomatoes.",
        "price_per_kg": 50.0,
        "category": "fruits",
        "image_url": "https://images.unsplash.com/photo-1546470427-2abef20b2c52?q=80&w=800&auto=format&fit=crop",
    },
    {
        "name": "Potato",
        "description": "All-purpose potatoes.",
        "price_per_kg": 35.0,
        "category": "root",
        "image_url": "https://images.unsplash.com/photo-1570233476081-60c2a2a55fe4?q=80&w=800&auto=format&fit=crop",
    },
    {
        "name": "Cucumber",
        "description": "Cool and refreshing cucumbers.",
        "price_per_kg": 45.0,
        "category": "fruits",
        "image_url": "https://images.unsplash.com/photo-1613743983595-cf000a6b8ec3?q=80&w=800&auto=format&fit=crop",
    },
    {
        "name": "Cabbage",
        "description": "Crisp green cabbage.",
        "price_per_kg": 40.0,
        "category": "leafy",
        "image_url": "https://images.unsplash.com/photo-1601000938259-d3c9d0948a3a?q=80&w=800&auto=format&fit=crop",
    },
    {
        "name": "Beetroot",
        "description": "Sweet earthy beets.",
        "price_per_kg": 70.0,
        "category": "root",
        "image_url": "https://images.unsplash.com/photo-1510627498534-cf7e9002facc?q=80&w=800&auto=format&fit=crop",
    },
    {
        "name": "Organic Lettuce",
        "description": "Organic crunchy lettuce.",
        "price_per_kg": 120.0,
        "category": "organic",
        "image_url": "https://images.unsplash.com/photo-1566786630087-54f3ad504fcd?q=80&w=800&auto=format&fit=crop",
    },
]


def ensure_seed_products():
    if db is None:
        return
    count = db["product"].count_documents({})
    if count == 0:
        for p in SAMPLE_PRODUCTS:
            prod = ProductSchema(**p)
            create_document("product", prod)


# ------------ Routes -------------
@app.on_event("startup")
def on_startup():
    ensure_seed_products()


@app.get("/", tags=["health"])
def read_root():
    return {"message": "VegHolic API running"}


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/schema", tags=["schema"])
def get_schema():
    # Basic schemas info for viewer
    return {
        "collections": ["user", "product", "address", "cartitem", "order"],
    }


# ---------- Auth (Mock OTP) ----------
@app.post("/api/auth/request-otp", tags=["auth"])
def request_otp(payload: OTPRequest):
    # In production, send OTP via SMS. Here we return a static OTP for demo.
    return {"phone": payload.phone, "otp": "1234", "message": "Use 1234 to login (demo)"}


@app.post("/api/auth/verify-otp", tags=["auth"])
def verify_otp(payload: OTPVerify):
    if payload.otp != "1234":
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # Find existing user
    existing = db["user"].find_one({"phone": payload.phone})
    if existing:
        token = existing.get("token") or payload.phone + "-token"
        db["user"].update_one({"_id": existing["_id"]}, {"$set": {"token": token, "name": existing.get("name") or payload.name}})
        user_id = str(existing["_id"])
    else:
        user = UserSchema(phone=payload.phone, name=payload.name or "VegHolic User")
        new_id = create_document("user", user)
        token = payload.phone + "-token"
        db["user"].update_one({"_id": oid(new_id)}, {"$set": {"token": token}})
        user_id = new_id

    return {"user_id": user_id, "token": token}


# ---------- Products ----------
@app.get("/api/products", tags=["products"])
def list_products(category: Optional[str] = Query(default=None)):
    filt: Dict[str, Any] = {}
    if category:
        filt["category"] = category
    products = get_documents("product", filt, None)
    return ObjectIdEncoder.encode(products)


@app.get("/api/products/{product_id}", tags=["products"])
def get_product(product_id: str):
    prod = db["product"].find_one({"_id": oid(product_id)})
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    return ObjectIdEncoder.encode(prod)


# ---------- Cart ----------
WEIGHT_MULTIPLIER = {
    "250g": 0.25,
    "500g": 0.5,
    "1kg": 1.0,
    "2kg": 2.0,
}


def calc_price(price_per_kg: float, variant: str) -> float:
    m = WEIGHT_MULTIPLIER.get(variant, 1.0)
    return round(price_per_kg * m, 2)


@app.get("/api/cart", tags=["cart"])
def get_cart(user_id: str = Query(...)):
    items = list(db["cartitem"].find({"user_id": user_id}))
    return ObjectIdEncoder.encode(items)


@app.post("/api/cart/add", tags=["cart"])
def add_to_cart(payload: AddToCartRequest):
    prod = db["product"].find_one({"_id": oid(payload.product_id)})
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    unit_price = calc_price(prod.get("price_per_kg", 0.0), payload.variant)

    existing = db["cartitem"].find_one({
        "user_id": payload.user_id,
        "product_id": payload.product_id,
        "variant": payload.variant,
    })
    if existing:
        new_qty = max(1, int(existing.get("qty", 1)) + payload.qty)
        db["cartitem"].update_one({"_id": existing["_id"]}, {"$set": {"qty": new_qty}})
        item_id = str(existing["_id"])
    else:
        item = CartItemSchema(
            user_id=payload.user_id,
            product_id=payload.product_id,
            product_name=prod.get("name"),
            image_url=prod.get("image_url"),
            variant=payload.variant,
            qty=payload.qty,
            price=unit_price,
        )
        item_id = create_document("cartitem", item)

    return {"item_id": item_id}


@app.post("/api/cart/{item_id}/qty", tags=["cart"])
def update_cart_qty(item_id: str, payload: UpdateCartQty):
    if payload.qty < 1:
        raise HTTPException(status_code=400, detail="Quantity must be >= 1")
    res = db["cartitem"].update_one({"_id": oid(item_id)}, {"$set": {"qty": int(payload.qty)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cart item not found")
    return {"ok": True}


@app.delete("/api/cart/{item_id}", tags=["cart"])
def remove_cart_item(item_id: str):
    res = db["cartitem"].delete_one({"_id": oid(item_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cart item not found")
    return {"ok": True}


# ---------- Addresses ----------
@app.get("/api/addresses", tags=["address"])
def list_addresses(user_id: str = Query(...)):
    items = list(db["address"].find({"user_id": user_id}))
    return ObjectIdEncoder.encode(items)


@app.post("/api/addresses", tags=["address"])
def create_address(payload: AddressCreate):
    addr_id = create_document("address", payload)
    if payload.is_default:
        db["address"].update_many({"user_id": payload.user_id, "_id": {"$ne": oid(addr_id)}}, {"$set": {"is_default": False}})
        db["user"].update_one({"_id": oid(payload.user_id)}, {"$set": {"default_address_id": addr_id}})
    return {"address_id": addr_id}


@app.patch("/api/addresses/{address_id}", tags=["address"])
def update_address(address_id: str, payload: dict):
    if not payload:
        return {"ok": True}
    db["address"].update_one({"_id": oid(address_id)}, {"$set": payload})
    if payload.get("is_default"):
        addr = db["address"].find_one({"_id": oid(address_id)})
        if addr:
            db["address"].update_many({"user_id": addr["user_id"], "_id": {"$ne": oid(address_id)}}, {"$set": {"is_default": False}})
            db["user"].update_one({"_id": oid(addr["user_id"])}, {"$set": {"default_address_id": address_id}})
    return {"ok": True}


@app.delete("/api/addresses/{address_id}", tags=["address"])
def delete_address(address_id: str):
    res = db["address"].delete_one({"_id": oid(address_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Address not found")
    return {"ok": True}


# ---------- Orders ----------
ORDER_STATUSES = ["Order Placed", "Packed", "On The Way", "Delivered"]


@app.post("/api/orders/create", tags=["orders"])
def create_order(payload: CreateOrderRequest):
    user_id = payload.user_id
    cart = list(db["cartitem"].find({"user_id": user_id}))
    if not cart:
        raise HTTPException(status_code=400, detail="Cart is empty")
    total = 0.0
    for it in cart:
        total += float(it.get("price", 0.0)) * int(it.get("qty", 1))
    order = OrderSchema(
        user_id=user_id,
        items=cart,
        address_id=payload.address_id,
        payment_method=payload.payment_method,
        total_amount=round(total, 2),
        status=ORDER_STATUSES[0],
        eta="30-45 mins",
    )
    order_id = create_document("order", order)
    # Clear cart
    db["cartitem"].delete_many({"user_id": user_id})
    return {"order_id": order_id}


@app.get("/api/orders", tags=["orders"])
def list_orders(user_id: str = Query(...)):
    orders = list(db["order"].find({"user_id": user_id}).sort("created_at", -1))
    return ObjectIdEncoder.encode(orders)


@app.get("/api/orders/{order_id}", tags=["orders"])
def get_order(order_id: str):
    o = db["order"].find_one({"_id": oid(order_id)})
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    return ObjectIdEncoder.encode(o)


@app.get("/api/orders/{order_id}/track", tags=["orders"])
def track_order(order_id: str):
    o = db["order"].find_one({"_id": oid(order_id)})
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    # delivery_boy_location_map is out of scope; return mock coordinates
    tracking = {
        "status": o.get("status", ORDER_STATUSES[0]),
        "steps": ORDER_STATUSES,
        "active_index": ORDER_STATUSES.index(o.get("status", ORDER_STATUSES[0])),
        "eta": o.get("eta", "30-45 mins"),
        "location": {"lat": 12.9716, "lng": 77.5946},
    }
    return tracking


@app.post("/api/orders/{order_id}/advance", tags=["orders"])
def advance_order(order_id: str):
    o = db["order"].find_one({"_id": oid(order_id)})
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    status = o.get("status", ORDER_STATUSES[0])
    try:
        idx = ORDER_STATUSES.index(status)
    except ValueError:
        idx = 0
    new_status = ORDER_STATUSES[min(idx + 1, len(ORDER_STATUSES) - 1)]
    db["order"].update_one({"_id": o["_id"]}, {"$set": {"status": new_status}})
    return {"status": new_status}


# ---------- Profile ----------
@app.get("/api/profile", tags=["profile"])
def get_profile(user_id: str = Query(...)):
    u = db["user"].find_one({"_id": oid(user_id)})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    addresses = list(db["address"].find({"user_id": user_id}))
    orders = list(db["order"].find({"user_id": user_id}).limit(5).sort("created_at", -1))
    return {
        "user": ObjectIdEncoder.encode(u),
        "addresses": ObjectIdEncoder.encode(addresses),
        "recent_orders": ObjectIdEncoder.encode(orders),
    }


@app.get("/test", tags=["health"])
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
