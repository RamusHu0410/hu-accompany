from uuid import UUID

from sqlalchemy.orm import Session

from db.models import Composer, Piece, ScoreSource


def create_composer(db: Session, name: str) -> Composer:
    composer = Composer(name=name)
    db.add(composer)  # Queue INSERT
    db.commit()  # Save it in Postgres
    db.refresh(composer)  # Retrieve generated id/timestamps
    return composer


def get_composer(db: Session, composer_id: UUID) -> Composer | None:
    return db.get(Composer, composer_id)


def create_piece(db: Session, composer_id: UUID, title: str) -> Piece:
    piece = Piece(composer_id=composer_id, title=title)
    db.add(piece)
    db.commit()
    db.refresh(piece)
    return piece


def save_musicxml(db: Session, piece_id: UUID, xml: str) -> ScoreSource:
    score = ScoreSource(piece_id=piece_id, content=xml)
    db.add(score)
    db.commit()
    db.refresh(score)
    return score


def get_musicxml(db: Session, score_id: UUID) -> ScoreSource | None:
    return db.get(ScoreSource, score_id)
