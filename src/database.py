from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite (локальный файл)
DATABASE_URL = "sqlite:///items.db"

engine = create_engine(DATABASE_URL, echo=False)  # echo=True для логов запросов
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
