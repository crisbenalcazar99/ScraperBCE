from sqlalchemy import create_engine

from config.settings import DB_CONNECTION_STRING

engine = create_engine(DB_CONNECTION_STRING)

