import re

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Product, User, VectorOutbox


def csrf_token(response):
    match = re.search(r'<meta name="csrf-token" content="([^"]+)">', response.text)
    assert match
    return match.group(1)


def test_admin_can_edit_product_and_queue_vector_sync(client):
    with SessionLocal() as db:
        admin = User(email="editor@example.com", password_hash=hash_password("strong-password"), role="admin")
        product = Product(title="Old title", description="Old course description", category="AI", price=10)
        db.add_all([admin, product])
        db.commit()
        product_id = product.id

    token = csrf_token(client.get("/login"))
    client.post("/login", data={"email": "editor@example.com", "password": "strong-password", "csrf_token": token})
    edit_page = client.get(f"/admin/products/{product_id}/edit")
    assert edit_page.status_code == 200
    token = csrf_token(edit_page)
    response = client.post(
        f"/admin/products/{product_id}/edit",
        data={
            "csrf_token": token,
            "title": "Updated course",
            "provider": "SmartReco",
            "track": "data",
            "level": "advanced",
            "category": "Data",
            "price": "49",
            "currency": "usd",
            "rating": "4.8",
            "tags": "python, analytics",
            "syllabus": "Models and dashboards",
            "description": "Updated practical course description.",
            "image_url": "",
            "is_active": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        product = db.get(Product, product_id)
        assert (product.title, product.currency, product.tags) == ("Updated course", "USD", ["python", "analytics"])
        job = db.query(VectorOutbox).filter_by(product_id=product_id).one()
        assert (job.operation, job.status) == ("upsert", "pending")
