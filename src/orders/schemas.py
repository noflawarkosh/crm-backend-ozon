import datetime
from typing import Optional
from pydantic import BaseModel, constr
from products.schemas import ProductReadSchema, ProductSizeReadSchema


class OrdersOrderCreateModel(BaseModel):
    ozon_keyword: str
    dt_planed: datetime.datetime
    product_id: int


class OrdersOrderReadModel(BaseModel):
    id: int

    ozon_keyword: str
    ozon_price: Optional[int] = None

    status: int
    description: Optional[str]

    dt_planed: datetime.datetime
    dt_ordered: Optional[datetime.datetime]
    dt_delivered: Optional[datetime.datetime]
    dt_collected: Optional[datetime.datetime]


    product: 'ProductReadSchema'
