from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class UserContact(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_contacts"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "contact_user_id", name="uq_user_contacts_owner_contact"),
    )

    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contact_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
