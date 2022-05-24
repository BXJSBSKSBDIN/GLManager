import app.domain.entities
from app.data.config import Base,  DBConnection

with DBConnection() as db:
    Base.metadata.create_all(db.engine)

import app.modules