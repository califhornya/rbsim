from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .schema import Base

def make_engine(db_path: str = "riftbound.db"):
    engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
    Base.metadata.create_all(engine)
    return engine

def make_session(db_path: str = "riftbound.db"):
    engine = make_engine(db_path)
    return sessionmaker(bind=engine, expire_on_commit=False)()
