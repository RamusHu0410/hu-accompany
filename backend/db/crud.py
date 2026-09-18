# Create, Write, Update, Delete

# crud.py
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from db.models import Composer, Piece, ScoreSource


# --- Composer ---


def get_composer_by_name(db: Session, name: str) -> Composer | None:
    return db.execute(
        select(Composer).where(Composer.name == name)
    ).scalar_one_or_none()


def create_composer(db: Session, name: str) -> Composer:
    composer = Composer(name=name)
    db.add(composer)
    db.flush()  # assigns composer.id without ending the transaction
    return composer


def get_or_create_composer(db: Session, name: str) -> Composer:
    existing = get_composer_by_name(db, name)
    if existing:
        return existing
    return create_composer(db, name)


# --- Piece ---


def get_piece_by_title(db: Session, composer_id: UUID, title: str) -> Piece | None:
    return db.execute(
        select(Piece).where(Piece.composer_id == composer_id, Piece.title == title)
    ).scalar_one_or_none()


def create_piece(db: Session, composer_id: UUID, title: str) -> Piece:
    piece = Piece(composer_id=composer_id, title=title)
    db.add(piece)
    db.flush()
    return piece


def get_or_create_piece(db: Session, composer_id: UUID, title: str) -> Piece:
    existing = get_piece_by_title(db, composer_id, title)
    if existing:
        return existing
    return create_piece(db, composer_id, title)


# --- ScoreSource (the actual MusicXML content) ---


def get_score_by_piece_id(db: Session, piece_id: UUID) -> ScoreSource | None:
    return db.execute(
        select(ScoreSource).where(ScoreSource.piece_id == piece_id)
    ).scalar_one_or_none()


def get_musicxml(db: Session, score_id: UUID) -> ScoreSource | None:
    return db.get(ScoreSource, score_id)


def create_score(db: Session, piece_id: UUID, xml: str) -> ScoreSource:
    score = ScoreSource(piece_id=piece_id, content=xml)
    db.add(score)
    db.flush()
    return score


# --- Top-level: the one function pdmx.py actually calls ---


def get_or_create_score(
    db: Session, composer_name: str, piece_title: str, xml_content: str
) -> tuple[ScoreSource, bool]:
    """
    Looks up composer -> piece -> score in that order, creating whichever
    ones don't exist yet. Returns (score, created) where `created` is False
    if a score for this piece was already stored (xml_content is ignored
    in that case), or True if a new one was just inserted.
    """
    composer = get_or_create_composer(db, composer_name)
    piece = get_or_create_piece(db, composer.id, piece_title)

    existing_score = get_score_by_piece_id(db, piece.id)
    if existing_score:
        return existing_score, False

    score = create_score(db, piece.id, xml_content)
    db.commit()  # one commit for the whole transaction
    db.refresh(score)
    return score, True
