from sqlalchemy import create_engine

from config.settings import DB_CONNECTION_STRING, DB_CONNECTION_STRING_COLA

engine = create_engine(DB_CONNECTION_STRING)
engine_cola = create_engine(DB_CONNECTION_STRING_COLA)

