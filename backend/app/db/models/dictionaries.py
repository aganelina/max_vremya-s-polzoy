from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class University(Base):

    __tablename__ = "universities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

class District(Base):

    __tablename__ = "districts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

class DistrictAdjacency(Base):

    __tablename__ = "district_adjacency"

    district_id: Mapped[str] = mapped_column(
        ForeignKey("districts.id", ondelete="CASCADE"), primary_key=True
    )
    neighbor_id: Mapped[str] = mapped_column(
        ForeignKey("districts.id", ondelete="CASCADE"), primary_key=True
    )
