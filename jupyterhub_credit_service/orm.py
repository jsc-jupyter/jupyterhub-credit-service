from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, Unicode
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import MutableDict

Base = declarative_base()


class UserCredits(Base):
    """Table for storing per-user credits."""

    __tablename__ = "user_credits"

    name = Column(Unicode, primary_key=True)
    balance = Column(Integer, default=0)
    cap = Column(Integer, default=100)
    grant_value = Column(Integer, default=5)
    grant_interval = Column(Integer, default=300)
    grant_last_update = Column(DateTime, default=datetime.now())
    spawner_bills = Column(MutableDict.as_mutable(JSON), default=dict)

    @classmethod
    def get_user(cls, db, user_name):
        orm_user_credits = db.query(cls).filter(cls.name == user_name).first()
        return orm_user_credits
