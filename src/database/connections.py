"""
Gestión de engines SQLAlchemy.

Uso:
    from src.database.connection import get_engine

    engine = get_engine()                        # usa PRIMARY_DB
    engine_cola = get_engine("procesos_bi")      # alias explícito
"""
from sqlalchemy import create_engine

from config.settings import DB_CONNECTION_STRING


engine = create_engine(DB_CONNECTION_STRING)

