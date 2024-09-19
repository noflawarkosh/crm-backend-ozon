from typing import Annotated
from sqlalchemy import text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import datetime

from payments.models import Base

pk = Annotated[int, mapped_column(primary_key=True)]
dt = Annotated[datetime.datetime, mapped_column(server_default=text('NOW()'))]


class ProductModel(Base):
    __tablename__ = 'products_product'

    id: Mapped[pk]
    added_at: Mapped[dt]
    updated_at: Mapped[dt]
    status: Mapped[int]

    ozon_article: Mapped[str]
    ozon_title: Mapped[str]
    ozon_size: Mapped[str | None]
    ozon_price: Mapped[int | None]

    barcode: Mapped[str | None]
    media: Mapped[str | None]

    # FK
    org_id: Mapped[int] = mapped_column(
        ForeignKey('organization.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    # Relationships
    organization: Mapped['OrganizationModel'] = relationship(lazy='noload')


class ReviewModel(Base):
    __tablename__ = 'products_review'

    id: Mapped[pk]
    advs: Mapped[str | None]
    disadvs: Mapped[str | None]
    text: Mapped[str | None]
    status: Mapped[int]
    description: Mapped[str | None]
    stars: Mapped[int]
    is_express: Mapped[bool] = mapped_column(default=False)

    # FK
    product_id: Mapped[int] = mapped_column(
        ForeignKey('products_product.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    # Relationships
    media: Mapped[list['ReviewMediaModel']] = relationship(lazy='noload')
    product: Mapped['ProductModel'] = relationship(lazy='noload')


class ReviewMediaModel(Base):
    __tablename__ = 'products_review_media'

    id: Mapped[pk]
    media: Mapped[str | None]

    # FK
    review_id: Mapped[int] = mapped_column(
        ForeignKey('products_review.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    review: Mapped['ReviewModel'] = relationship(lazy='noload')
