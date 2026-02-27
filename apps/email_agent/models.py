"""
email_agent — SQLAlchemy models.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class EmailMessage(Base):
    __tablename__ = "email_messages"

    id = Column(String(36), primary_key=True)
    message_id = Column(String(512), index=True, nullable=True)
    folder = Column(String(128), default="INBOX")
    from_addr = Column(String(512), nullable=True)
    to_addr = Column(Text, nullable=True)
    cc_addr = Column(Text, nullable=True)
    subject = Column(Text, nullable=True)
    date = Column(DateTime(timezone=True), nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    flags = Column(String(256), nullable=True)
    raw_object_key = Column(String(512), nullable=True)
    attachment_count = Column(Integer, default=0)
    tenant_id = Column(String(64), default="nexus")
    env = Column(String(32), default="prod")
    created_at = Column(DateTime(timezone=True), nullable=True)


class EmailAttachment(Base):
    __tablename__ = "email_attachments"

    id = Column(String(36), primary_key=True)
    message_id = Column(String(36), index=True, nullable=False)
    filename = Column(String(512), nullable=True)
    content_type = Column(String(256), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    object_key = Column(String(512), nullable=True)
