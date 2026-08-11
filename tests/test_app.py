import re

from app.auth import hash_password
from app.database import SessionLocal
from app.models import (
    AgentRun,
    BehaviorEvent,
    CareerPlan,
    CareerProfile,
    CareerVectorOutbox,
    Enrollment,
    LearningVectorOutbox,
    Product,
    User,
)
from app.schemas import CareerPathPayload


def csrf_token(client, path="/register"):
    response = client.get(path)
    match = re.search(r'<meta name="csrf-token" content="([^"]+)">', response.text)
    assert match
    return match.group(1)


def register(client, email="learner@example.com"):
    token = csrf_token(client)
    return client.post(
        "/register",
        data={"email": email, "password": "strong-password", "csrf_token": token},
        follow_redirects=False,
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_cody_ai_page(client):
    response = client.get("/cody-ai")
    assert response.status_code == 200
    assert "Learn with <span>Cody AI</span>" in response.text
    assert 'name="q"' in response.text


def test_cody_ask_falls_back_when_vector_search_fails(client, monkeypatch):
    class BrokenVectors:
        def search(self, _query, limit):
            raise ValueError("Chroma collection is unavailable")

    with SessionLocal() as db:
        db.add(Product(title="Data Engineering", description="Build reliable data pipelines.", category="Data", price=0))
        db.commit()
    monkeypatch.setattr("app.main.vector_store", lambda: BrokenVectors())
    token = csrf_token(client, "/cody-ai")

    response = client.post("/cody-ai/ask", data={"question": "data engineering", "csrf_token": token})

    assert response.status_code == 200
    assert "Data Engineering" in response.text


def test_registration_creates_user_and_session(client):
    response = register(client)
    assert response.status_code == 303
    with SessionLocal() as db:
        user = db.query(User).filter_by(email="learner@example.com").one()
        assert user.role == "user"


def test_registration_rejects_missing_csrf_token(client):
    response = client.post(
        "/register",
        data={"email": "attacker@example.com", "password": "strong-password"},
    )
    assert response.status_code == 403


def test_events_require_authentication(client):
    response = client.post(
        "/api/events",
        json={"events": [{"event_type": "search", "search_query": "RAG", "session_id": "s1"}]},
    )
    assert response.status_code == 401


def test_event_batch_is_stored(client):
    register(client)
    token = csrf_token(client, "/")
    response = client.post(
        "/api/events",
        headers={"X-CSRF-Token": token},
        json={
            "events": [
                {"event_type": "search", "search_query": "agentic AI", "session_id": "s1"},
                {"event_type": "category_view", "category": "AI", "session_id": "s1"},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json() == {"accepted": 2}
    with SessionLocal() as db:
        assert db.query(BehaviorEvent).count() == 2


def test_event_batch_rejects_missing_csrf_token(client):
    register(client)
    response = client.post(
        "/api/events",
        json={"events": [{"event_type": "search", "session_id": "s1"}]},
    )
    assert response.status_code == 403


def test_admin_route_rejects_regular_user(client):
    register(client)
    assert client.get("/admin/products").status_code == 403
    assert client.get("/admin/agent-runs").status_code == 403


def test_admin_can_inspect_agent_runs(client):
    with SessionLocal() as db:
        admin = User(email="agent-admin@example.com", password_hash=hash_password("strong-password"), role="admin")
        learner = User(email="agent-learner@example.com", password_hash="unused")
        db.add_all([admin, learner])
        db.flush()
        db.add(AgentRun(user_id=learner.id, behavior_signature="behavior-123", path="personalized", status="failed", error="Mesh response validation failed"))
        db.commit()

    token = csrf_token(client, "/login")
    client.post("/login", data={"email": "agent-admin@example.com", "password": "strong-password", "csrf_token": token})
    page = client.get("/admin/agent-runs")
    courses_page = client.get("/admin/products")

    assert page.status_code == 200
    assert 'data-slot="sidebar-inset"' in page.text
    assert "agent-learner@example.com" in page.text
    assert "Mesh response validation failed" in page.text
    assert courses_page.status_code == 200
    assert 'data-slot="sidebar-inset"' in courses_page.text
    assert "Total courses" in courses_page.text
    assert 'class="active" href="/admin/products"' in courses_page.text


def test_catalog_page_lists_active_products(client):
    with SessionLocal() as db:
        db.add(
            Product(
                title="Production RAG",
                description="Build grounded retrieval applications.",
                category="AI",
                price=999,
            )
        )
        db.commit()
    response = client.get("/")
    assert response.status_code == 200
    assert "Production RAG" in response.text


def test_course_explorer_builds_facets_from_database(client):
    with SessionLocal() as db:
        db.add_all([
            Product(title="SQL Analytics", description="Learn practical SQL analytics.", category="Data", level="Beginner", price=0),
            Product(title="Secure APIs", description="Protect production web APIs.", category="Security", level="Advanced", price=49),
        ])
        db.commit()
    response = client.get("/courses?category=Data")
    assert response.status_code == 200
    assert "SQL Analytics" in response.text
    assert "Secure APIs" not in response.text
    assert "Data" in response.text
    assert "Security" in response.text


def test_start_course_creates_one_enrollment_and_vector_job(client):
    with SessionLocal() as db:
        course = Product(title="Agent Systems", description="Build practical agent systems.", category="AI", price=0)
        db.add(course)
        db.commit()
        product_id = course.id
    register(client)
    token = csrf_token(client, f"/products/{product_id}")
    first = client.post(f"/products/{product_id}/start", data={"csrf_token": token}, follow_redirects=False)
    second = client.post(f"/products/{product_id}/start", data={"csrf_token": token}, follow_redirects=False)
    assert first.status_code == 303
    assert second.status_code == 303
    with SessionLocal() as db:
        enrollment = db.query(Enrollment).one()
        assert enrollment.product_id == product_id
        assert enrollment.vector_status == "pending"
        assert db.query(LearningVectorOutbox).count() == 1
    page = client.get("/my-learning")
    assert page.status_code == 200
    assert "Agent Systems" in page.text


def test_product_page_exposes_behavior_tracking_marker(client):
    with SessionLocal() as db:
        course = Product(title="Tracked Course", description="A tracked course.", category="Data", price=0)
        db.add(course)
        db.commit()
        product_id = course.id
    register(client)

    page = client.get(f"/products/{product_id}")

    assert page.status_code == 200
    assert 'class="detail-hero product-detail track-data"' in page.text
    assert f'data-product-id="{product_id}"' in page.text


def test_my_learning_summarizes_stored_behavior_events(client):
    register(client)
    with SessionLocal() as db:
        user = db.query(User).filter_by(email="learner@example.com").one()
        course = Product(title="Web Developer Bootcamp", description="Build web apps.", category="Software", price=0)
        db.add(course)
        db.flush()
        db.add_all([
            BehaviorEvent(user_id=user.id, event_type="product_view", product_id=course.id, session_id="s1"),
            BehaviorEvent(user_id=user.id, event_type="product_view", product_id=course.id, session_id="s2"),
            BehaviorEvent(user_id=user.id, event_type="time_spent", product_id=course.id, event_metadata={"seconds": 68}, session_id="s2"),
        ])
        db.commit()

    page = client.get("/my-learning")

    assert page.status_code == 200
    assert "You spent 1m 8s reading" in page.text
    assert "You looked at Web Developer Bootcamp 2 times" in page.text
    assert "2 learning sessions so far" in page.text


def test_my_learning_shows_activity_empty_state(client):
    register(client)

    page = client.get("/my-learning")

    assert page.status_code == 200
    assert "What SmartReco has noticed" in page.text
    assert "Your activity story starts here" in page.text


def test_cody_builds_and_saves_grounded_career_path(client, monkeypatch):
    with SessionLocal() as db:
        course = Product(title="Applied ML", description="Build production machine learning systems.", category="AI", track="ai-ml", level="Intermediate", price=0)
        db.add(course)
        db.commit()
        product_id = course.id
    register(client)
    payload = CareerPathPayload.model_validate({
        "title": "Path to ML Engineer",
        "summary": "A practical route from Python foundations to production ML.",
        "target_role": "Machine Learning Engineer",
        "estimated_months": 8,
        "hero_message": "You are ready to build toward production ML.",
        "stages": [
            {"phase": "Foundations", "duration": "2 months", "goal": "Strengthen core skills", "skills": ["Python"], "course_ids": [product_id], "project": "Analysis portfolio", "certifications": [], "interview_prep": ["Python practice"]},
            {"phase": "Applied ML", "duration": "3 months", "goal": "Build models", "skills": ["ML"], "course_ids": [product_id], "project": "Prediction service", "certifications": [], "interview_prep": ["ML concepts"]},
            {"phase": "Production", "duration": "3 months", "goal": "Ship reliable systems", "skills": ["MLOps"], "course_ids": [product_id], "project": "Deployed ML system", "certifications": ["Optional cloud ML certification"], "interview_prep": ["System design"]},
        ],
    })
    monkeypatch.setattr("app.main.mesh.career_plan", lambda profile, products: payload)
    monkeypatch.setattr("app.main.scheduled_vector_sync", lambda: None)
    token = csrf_token(client, "/cody-ai")
    response = client.post("/cody-ai/career-path", data={"csrf_token": token, "experience": "Python developer", "current_skills": "Python, SQL", "career_interests": "Machine learning systems", "target_role": "Machine Learning Engineer", "skill_level": "Intermediate"}, follow_redirects=False)
    assert response.status_code == 303
    with SessionLocal() as db:
        assert db.query(CareerProfile).one().target_role == "Machine Learning Engineer"
        assert db.query(CareerPlan).one().stages[0]["course_ids"] == [product_id]
        assert db.query(CareerVectorOutbox).one().status == "pending"
