import datetime
from typing import Optional
from pydantic import BaseModel, constr


# Product Size schemas
class ProductSizeCreateSchema(BaseModel):
    wb_size_name: str | None
    wb_size_origName: str | None
    wb_size_optionId: int
    wb_in_stock: bool
    wb_price: int | None
    barcode: str | None
    is_active: bool


class ProductSizeReadSchema(ProductSizeCreateSchema):
    id: int
    product: Optional['ProductReadSchema']


# Product schemas
class ProductPOSTSchema(BaseModel):
    org_id: int
    ozon_url: str


class ProductCreateSchema(BaseModel):
    org_id: int
    wb_article: str
    wb_title: str


class ProductReadSchema(BaseModel):
    id: int
    added_at: datetime.datetime
    updated_at: datetime.datetime

    status: int
    ozon_article: str
    ozon_title: str
    ozon_size: str | None
    ozon_price: int
    barcode: str | None

    org_id: int
    media: Optional[str] = None


# Review schemas
class ReviewMediaReadSchema(BaseModel):
    id: int
    review_id: int
    media: str | None


class ReviewCreateSchema(BaseModel):
    advs: Optional[str] = None
    disadvs: Optional[str] = None
    text: Optional[str] = None
    product_id: Optional[int] = None
    is_express: bool = False
    stars: int


class ReviewUpdateSchema(BaseModel):
    id: int
    text: Optional[str] = None
    advs: Optional[str] = None
    disadvs: Optional[str] = None
    is_express: bool
    stars: int


class ReviewReadSchema(ReviewCreateSchema):
    id: int
    status: int
    description: Optional[str] = None
    is_express: bool

    media: Optional[list[ReviewMediaReadSchema]] = None
    product: Optional[ProductReadSchema]
