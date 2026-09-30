import os
from datetime import datetime, date

from sqlalchemy import (JSON, Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint,
                        create_engine, select)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def _database_url():
    url = os.environ.get("DATABASE_URL", "sqlite:///./analytics.db")
    # Render hands out postgres://... ; SQLAlchemy + psycopg3 wants postgresql+psycopg://
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


engine = create_engine(_database_url(), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Show(Base):
    __tablename__ = "shows"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. LEX26
    brand: Mapped[str] = mapped_column(String(16))                    # LEX / LNA / LME
    name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(40))                   # Europe / North America / Middle East
    year: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_code: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("show_code", "source_id", name="uq_show_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    show_code: Mapped[str] = mapped_column(String(16), index=True)
    source_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reg_type_raw: Mapped[str | None] = mapped_column(String(60), nullable=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    world_region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_function: Mapped[str | None] = mapped_column(String(120), nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(40), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    industry_group: Mapped[str | None] = mapped_column(String(40), nullable=True)
    buyer_supplier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    budget_responsibility: Mapped[str | None] = mapped_column(String(20), nullable=True)
    budget_band: Mapped[str | None] = mapped_column(String(40), nullable=True)
    products: Mapped[str | None] = mapped_column(Text, nullable=True)
    commercial_interest: Mapped[str | None] = mapped_column(String(60), nullable=True)
    attended: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    previous_attendee: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source_channel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IngestRun(Base):
    __tablename__ = "ingest_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    show_code: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    rows_in: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


DEFAULT_SHOWS = [
    Show(code="LEX26", brand="LEX", name="Lubricant Expo Europe 2026", region="Europe", year=2026,
         start_date=date(2026, 9, 15), end_date=date(2026, 9, 17), previous_code="LEX25"),
    Show(code="LNA26", brand="LNA", name="Lubricant Expo North America 2026", region="North America",
         year=2026, previous_code="LNA25"),
    Show(code="LME26", brand="LME", name="Lubricant Expo Middle East 2026", region="Middle East",
         year=2026, previous_code="LME25"),
]


def ensure_show(code, start_date=None, end_date=None):
    """Return the show, creating it from its code (e.g. LEX27) if it doesn't exist yet."""
    from .dictionary import BRANDS, parse_show_code
    code = code.strip().upper()
    with SessionLocal() as s:
        show = s.get(Show, code)
        if show:
            return show
        brand, year = parse_show_code(code)
        name, region = BRANDS.get(brand, (brand, "Other"))
        show = Show(code=code, brand=brand, name=f"{name} {year}", region=region, year=year,
                    start_date=start_date, end_date=end_date, previous_code=f"{brand}{(year - 1) % 100:02d}")
        s.add(show)
        s.commit()
        return show


def init_db():
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        existing = set(s.scalars(select(Show.code)))
        for show in DEFAULT_SHOWS:
            if show.code not in existing:
                s.add(Show(**{c.name: getattr(show, c.name) for c in Show.__table__.columns}))
        s.commit()
