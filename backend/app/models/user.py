from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import relationship

from .base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String(50), default="user")

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    analysis_configurations = relationship(
        "AnalysisConfiguration",
        back_populates="user",
        cascade="all, delete-orphan",
    )