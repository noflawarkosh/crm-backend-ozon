from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from auth.router import router as router_auth
from frontend.router import router as router_frontend

from orgs.router import router as router_orgs
from payments.router import router as router_payments
from products.router import router_products
from products.router import router_reviews
from orders.router import router as router_orders
from admin.router import router as admin_router
from picker.router import router as picker_router

app = FastAPI(title='GreedyBear')
app.mount('/static', StaticFiles(directory='frontend/static'), name='static')

app.include_router(router_auth)
app.include_router(router_orgs)
app.include_router(router_payments)
app.include_router(router_products)
app.include_router(router_reviews)
app.include_router(picker_router)
app.include_router(router_orders)
app.include_router(admin_router)
app.include_router(router_frontend)
