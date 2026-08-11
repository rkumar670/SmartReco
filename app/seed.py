from sqlalchemy import inspect, select, text

from app.auth import hash_password
from app.course_catalog import COURSES
from app.database import Base, SessionLocal, engine
from app.models import Product, User

PRODUCTS = [
    (
        "Agentic AI with LangGraph",
        "Build reliable stateful AI agents with explicit workflows, retrieval, and human review.",
        "Agentic AI",
        2499,
    ),
    (
        "Production RAG Systems",
        "Design retrieval pipelines with vector search, metadata filters, reranking, and evaluation.",
        "Generative AI",
        1999,
    ),
    (
        "FastAPI from Zero to Production",
        "Create tested Python APIs with authentication, SQLAlchemy, background jobs, and deployment.",
        "Backend",
        1499,
    ),
    (
        "Machine Learning Foundations",
        "Learn feature engineering, model evaluation, regression, classification, and practical ML.",
        "Machine Learning",
        1299,
    ),
    (
        "Data Engineering with Python",
        "Build dependable data pipelines, orchestration workflows, and analytics-ready datasets.",
        "Data Engineering",
        1799,
    ),
    (
        "LLM Observability in Practice",
        "Trace prompts, retrieval, tool calls, latency, quality, and production failures.",
        "MLOps",
        999,
    ),
]


SQLITE_PRODUCT_COLUMNS = {
    "provider": "VARCHAR(150) NOT NULL DEFAULT ''",
    "track": "VARCHAR(50) NOT NULL DEFAULT ''",
    "level": "VARCHAR(30) NOT NULL DEFAULT ''",
    "currency": "VARCHAR(3) NOT NULL DEFAULT 'INR'",
    "rating": "FLOAT NOT NULL DEFAULT 0",
    "tags": "JSON NOT NULL DEFAULT '[]'",
    "syllabus": "TEXT NOT NULL DEFAULT ''",
}


def ensure_product_columns() -> None:
    if engine.dialect.name != "sqlite" or not inspect(engine).has_table("products"):
        return
    existing = {column["name"] for column in inspect(engine).get_columns("products")}
    with engine.begin() as connection:
        for name, definition in SQLITE_PRODUCT_COLUMNS.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE products ADD COLUMN {name} {definition}"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_track ON products (track)"))


def seed() -> None:
    ensure_product_columns()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email == "admin@test.com")):
            db.add(
                User(
                    email="admin@test.com",
                    password_hash=hash_password("admin1234"),
                    role="admin",
                )
            )

        existing_titles = set(db.scalars(select(Product.title)))
        for title, description, category, price in PRODUCTS:
            if title not in existing_titles:
                db.add(
                    Product(
                        title=title,
                        description=description,
                        category=category,
                        track=category.lower().replace(" ", "-"),
                        price=price,
                        currency="INR",
                    )
                )

        for title, provider, track, level, price, rating, tags, syllabus, description in COURSES:
            product = db.scalar(select(Product).where(Product.title == title))
            if product is None:
                product = Product(title=title, description=description, category=track, price=price)
                db.add(product)
            product.provider = provider
            product.track = track
            product.level = level
            product.price = price
            product.currency = "USD"
            product.rating = rating
            product.tags = tags
            product.syllabus = syllabus
            product.description = description
            product.category = track
            product.vector_status = "pending"
        db.commit()


if __name__ == "__main__":
    seed()
