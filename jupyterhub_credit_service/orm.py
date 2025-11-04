from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, Unicode
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class CreditsProject(Base):
    """Table for storing per-project credits."""

    __tablename__ = "credits_project"

    name = Column(Unicode, primary_key=True)

    display_name = Column(Unicode)
    balance = Column(Integer, default=0)
    cap = Column(Integer, default=100)
    grant_value = Column(Integer, default=5)
    grant_interval = Column(Integer, default=300)
    grant_last_update = Column(DateTime, default=datetime.now)
    user_options = Column(MutableDict.as_mutable(JSON), default=dict, nullable=True)

    # One project - many user values
    credits_user_values = relationship("CreditsUserValues", back_populates="project")

    @classmethod
    def get_project(cls, db, project_name):
        return db.query(cls).filter(cls.name == project_name).first()


class CreditsUser(Base):
    """Table for storing per-user credits."""

    __tablename__ = "credits_user"

    name = Column(Unicode, primary_key=True)

    spawner_bills = Column(MutableDict.as_mutable(JSON), default=dict)

    # One user - many user values
    credits_user_values = relationship(
        "CreditsUserValues", back_populates="credits_user"
    )

    @classmethod
    def get_user(cls, db, user_name):
        return db.query(cls).filter(cls.name == user_name).first()


class CreditsUserValues(Base):
    """Table for storing per-user (+ per-project) credits."""

    __tablename__ = "credits_user_values"

    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(Unicode)
    balance = Column(Integer, default=0)
    cap = Column(Integer, default=100)
    grant_value = Column(Integer, default=5)
    grant_interval = Column(Integer, default=300)
    grant_last_update = Column(DateTime, default=datetime.now)
    user_options = Column(MutableDict.as_mutable(JSON), default=dict, nullable=True)

    # Foreign keys
    user_name = Column(Unicode, ForeignKey("credits_user.name"), nullable=False)
    project_name = Column(Unicode, ForeignKey("credits_project.name"))

    # Relationships
    credits_user = relationship("CreditsUser", back_populates="credits_user_values")
    project = relationship("CreditsProject", back_populates="credits_user_values")
