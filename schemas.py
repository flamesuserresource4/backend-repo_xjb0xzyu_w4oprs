"""
VegHolic Database Schemas

Each Pydantic model represents a MongoDB collection.
Collection name is the lowercase class name.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class User(BaseModel):
    phone: str = Field(..., description="Phone number used for login")
    name: Optional[str] = Field(None, description="Display name")
    email: Optional[str] = Field(None, description="Optional email")
    default_address_id: Optional[str] = Field(None, description="Default address _id as string")
    token: Optional[str] = Field(None, description="Session token for simple auth")


class Product(BaseModel):
    name: str = Field(..., description="Product name")
    description: Optional[str] = Field(None, description="Short description")
    price_per_kg: float = Field(..., ge=0, description="Base price per kg in INR")
    category: str = Field(..., description="Category: leafy, root, fruits, organic")
    image_url: Optional[str] = Field(None, description="Image URL")
    variants: List[str] = Field(default_factory=lambda: ["250g", "500g", "1kg", "2kg"], description="Weight options")


class Address(BaseModel):
    user_id: str = Field(..., description="Owner user's _id as string")
    name: str
    mobile: str
    pincode: str
    street: str
    city: str
    is_default: bool = False


class CartItem(BaseModel):
    user_id: str = Field(..., description="Owner user's _id as string")
    product_id: str
    product_name: str
    image_url: Optional[str] = None
    variant: str = Field("1kg", description="Selected weight option")
    qty: int = Field(1, ge=1, description="Quantity of the selected variant")
    price: float = Field(..., ge=0, description="Unit price for this variant")


class Order(BaseModel):
    user_id: str
    items: list
    address_id: str
    payment_method: str = Field(..., description="COD | UPI | Card")
    total_amount: float
    status: str = Field("Order Placed", description="Current status")
    eta: str = Field("30-45 mins", description="Estimated time of delivery")
