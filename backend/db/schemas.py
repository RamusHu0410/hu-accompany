from db.db import Base, engine
import db.models  # Ensures SQLAlchemy sees every table model

Base.metadata.create_all(engine)
print("Tables created.")
