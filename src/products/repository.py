from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload, joinedload

from database import async_session_factory
from products.models import ProductModel, ReviewModel, ReviewMediaModel
from products.schemas import ProductCreateSchema, ProductSizeCreateSchema, ReviewCreateSchema


class ReviewsRepository:

    @classmethod
    async def create_review(cls, review_schema: ReviewCreateSchema, filenames: list):

        try:
            async with async_session_factory() as session:

                # Add review
                review = ReviewModel(**review_schema.model_dump(), status=1)
                session.add(review)
                await session.flush()

                # Add review media
                for filename in filenames:
                    session.add(ReviewMediaModel(
                        review_id=review.id,
                        media=filename)
                    )

                await session.commit()

        finally:
            await session.close()

    @classmethod
    async def get_owned_by_org_id(cls, org_id: int) -> list[ReviewModel] | None:

        try:

            async with async_session_factory() as session:

                query = (
                    select(ReviewModel)
                    .options(
                        selectinload(ReviewModel.media),
                        selectinload(ReviewModel.size),
                        selectinload(ReviewModel.size, ProductSizeModel.product)
                    )
                    .join(ProductSizeModel)
                    .join(ProductModel)

                    .filter(ProductModel.org_id == org_id)
                    .filter(ProductModel.status != 3)
                )

                db_response = await session.execute(query)
                reviews = db_response.unique().scalars().all()

                return reviews

        finally:
            await session.close()
