from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, Unicode
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ProjectCredits(Base):
    """Table for storing per-project credits."""

    __tablename__ = "project_credits"

    name = Column(Unicode, primary_key=True)
    balance = Column(Integer, default=0)
    cap = Column(Integer, default=100)
    grant_value = Column(Integer, default=5)
    grant_interval = Column(Integer, default=300)
    grant_last_update = Column(DateTime, default=datetime.now())

    users = relationship("UserCredits", back_populates="project")

    @classmethod
    def get_project(cls, db, project_name):
        orm_project_credits = db.query(cls).filter(cls.name == project_name).first()
        return orm_project_credits


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

    # Optional foreign key (nullable=True)
    project_name = Column(Unicode, ForeignKey("project_credits.name"), nullable=True)

    # Many-to-one relationship
    project = relationship("ProjectCredits", back_populates="users")

    @classmethod
    def get_user(cls, db, user_name):
        orm_user_credits = db.query(cls).filter(cls.name == user_name).first()
        return orm_user_credits
