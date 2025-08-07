from . import stock
from . import healthcheck  

routers = [
    stock.router,
    healthcheck.router
]