from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.db import Base


class Composer(Base):
    __tablename__ = "composers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    pieces: Mapped[list["Piece"]] = relationship(
        back_populates="composer", cascade="all, delete-orphan"
    )


class Piece(Base):
    __tablename__ = "pieces"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    composer_id: Mapped[UUID] = mapped_column(
        ForeignKey("composers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    composer: Mapped["Composer"] = relationship(back_populates="pieces")
    scores: Mapped[list["ScoreSource"]] = relationship(
        back_populates="piece", cascade="all, delete-orphan"
    )


class ScoreSource(Base):
    __tablename__ = "score_sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    piece_id: Mapped[UUID] = mapped_column(
        ForeignKey("pieces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    format: Mapped[str] = mapped_column(String(30), default="musicxml")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(default=1)

    piece: Mapped["Piece"] = relationship(back_populates="scores")
