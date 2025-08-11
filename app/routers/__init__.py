from . import healthcheck, stock

routers = [
    stock.router,
    healthcheck.router
]