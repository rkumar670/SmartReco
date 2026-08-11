import secrets
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import logfire
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth import current_user, hash_password, require_admin, require_user, verify_password
from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.mesh import MeshClient
from app.models import (
    AgentRun,
    BehaviorEvent,
    CareerPlan,
    CareerProfile,
    Enrollment,
    Product,
    Recommendation,
    User,
)
from app.recommendations import generate_recommendation, lexical_rank, should_generate
from app.schema_migrations import ensure_event_id_column
from app.schemas import EventBatchIn
from app.vector_outbox import (
    enqueue_career_vector,
    enqueue_learning_vector,
    enqueue_vector_operation,
    process_vector_outbox,
)
from app.vectors import ProductVectors

settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
mesh = MeshClient(settings)
vectors: ProductVectors | None = None
scheduler = BackgroundScheduler(timezone="UTC")


def learning_activity(events: list[BehaviorEvent], products: dict[int, Product]) -> list[dict[str, str]]:
    views: Counter[int] = Counter()
    reading_seconds: Counter[int] = Counter()
    category_products: defaultdict[str, set[int]] = defaultdict(set)
    sessions = set()
    for event in events:
        if event.event_type != "recommendation_impression":
            sessions.add(event.session_id)
        product = products.get(event.product_id)
        if event.event_type == "product_view" and product:
            views[product.id] += 1
            category_products[product.category].add(product.id)
        if event.event_type == "time_spent" and product:
            reading_seconds[product.id] += max(0, int(event.event_metadata.get("seconds", 0)))

    activity = []
    for product_id, seconds in reading_seconds.most_common():
        if seconds < 5:
            continue
        minutes, remaining = divmod(seconds, 60)
        duration = f"{minutes}m {remaining}s" if minutes else f"{remaining}s"
        activity.append({"kind": "time", "text": f"You spent {duration} reading ‘{products[product_id].title}’"})
    for product_id, count in views.most_common():
        if count >= 2:
            activity.append({"kind": "views", "text": f"You looked at {products[product_id].title} {count} times"})
    if len(sessions) > 1:
        activity.append({"kind": "return", "text": f"You keep coming back to SmartReco — {len(sessions)} learning sessions so far"})
    for category, product_ids in sorted(category_products.items(), key=lambda item: len(item[1]), reverse=True):
        if len(product_ids) >= 2:
            label = category.lower().replace("-", " ")
            activity.append({"kind": "category", "text": f"You opened {len(product_ids)} {label} courses"})
    return activity[:10]


def configure_observability(app: FastAPI) -> None:
    logfire.configure(service_name="smartreco", send_to_logfire="if-token-present")
    logfire.instrument_fastapi(
        app,
        request_attributes_mapper=lambda _request, attributes: {
            "errors": attributes.get("errors", [])
        },
    )
    logfire.instrument_sqlalchemy(engine=engine)


def vector_store() -> ProductVectors:
    global vectors
    if vectors is None:
        vectors = ProductVectors(settings, mesh)
    return vectors


def generate_for_user(user_id: int) -> None:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not should_generate(db, user_id, settings):
            return
        try:
            generate_recommendation(db, user, settings, mesh, vector_store())
        except (RuntimeError, ValueError) as error:
            logfire.warn("recommendation skipped", user_id=user_id, reason=str(error))


def scheduled_recommendations() -> None:
    with SessionLocal() as db:
        user_ids = list(db.scalars(select(User.id)))
    for user_id in user_ids:
        generate_for_user(user_id)


def scheduled_vector_sync() -> None:
    with SessionLocal() as db:
        process_vector_outbox(db, vector_store())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    ensure_event_id_column(engine)
    scheduler.add_job(
        scheduled_recommendations,
        "interval",
        minutes=15,
        id="recommendations",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    scheduler.add_job(
        scheduled_vector_sync,
        "interval",
        minutes=1,
        id="vector-outbox",
        replace_existing=True,
        max_instances=1,
    )
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="SmartReco", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
configure_observability(app)


def page_context(request: Request, db: Session, **values) -> dict:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return {"request": request, "user": current_user(request, db), "csrf_token": token, **values}


def verify_csrf(request: Request, submitted_token: str | None) -> None:
    session_token = request.session.get("csrf_token")
    if not session_token or not submitted_token or not secrets.compare_digest(
        session_token, submitted_token
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")


def require_form_csrf(request: Request, csrf_token: str | None = Form(default=None)) -> None:
    verify_csrf(request, csrf_token)


def require_header_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    user = require_user(request, db)
    verify_csrf(request, x_csrf_token)
    return user


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, background_tasks: BackgroundTasks, q: str = "", db: Session = Depends(get_db)):
    query = select(Product).where(Product.is_active.is_(True)).order_by(Product.created_at.desc())
    if q:
        query = query.where(
            or_(
                Product.title.ilike(f"%{q}%"),
                Product.description.ilike(f"%{q}%"),
                Product.category.ilike(f"%{q}%"),
            )
        )
    products = list(db.scalars(query))
    user = current_user(request, db)
    recommendation = None
    if user:
        recommendation = db.scalar(
            select(Recommendation)
            .where(Recommendation.user_id == user.id)
            .order_by(Recommendation.created_at.desc())
        )
        if not recommendation:
            background_tasks.add_task(generate_for_user, user.id)
    return templates.TemplateResponse(
        request,
        "home.html",
        page_context(
            request,
            db,
            products=products,
            recommendation=recommendation,
            search_query=q,
        ),
    )


@app.get("/courses", response_class=HTMLResponse)
def courses(
    request: Request,
    q: str = "",
    category: str = "",
    level: str = "",
    sort: str = "popular",
    db: Session = Depends(get_db),
):
    query = select(Product).where(Product.is_active.is_(True))
    if q:
        query = query.where(or_(Product.title.ilike(f"%{q}%"), Product.description.ilike(f"%{q}%"), Product.category.ilike(f"%{q}%")))
    if category:
        query = query.where(Product.category == category)
    if level:
        query = query.where(Product.level == level)
    products = list(db.scalars(query))
    enrollment_counts = dict(db.execute(select(Enrollment.product_id, func.count(Enrollment.id)).group_by(Enrollment.product_id)).all())
    if sort == "rating":
        products.sort(key=lambda product: product.rating, reverse=True)
    elif sort == "newest":
        products.sort(key=lambda product: product.created_at, reverse=True)
    elif sort == "price":
        products.sort(key=lambda product: product.price)
    else:
        products.sort(key=lambda product: (enrollment_counts.get(product.id, 0), product.rating), reverse=True)
    categories = list(db.execute(select(Product.category, func.count(Product.id)).where(Product.is_active.is_(True)).group_by(Product.category).order_by(Product.category)).all())
    levels = list(db.execute(select(Product.level, func.count(Product.id)).where(Product.is_active.is_(True), Product.level != "").group_by(Product.level).order_by(Product.level)).all())
    return templates.TemplateResponse(
        request,
        "courses.html",
        page_context(request, db, products=products, categories=categories, levels=levels, enrollment_counts=enrollment_counts, total_products=sum(count for _, count in categories), search_query=q, selected_category=category, selected_level=level, selected_sort=sort),
    )


@app.get("/products/{product_id}", response_class=HTMLResponse)
def product_page(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    user = current_user(request, db)
    enrollment = None
    if user:
        enrollment = db.scalar(
            select(Enrollment).where(
                Enrollment.user_id == user.id,
                Enrollment.product_id == product.id,
            )
        )
    return templates.TemplateResponse(
        request,
        "product.html",
        page_context(request, db, product=product, enrollment=enrollment),
    )


@app.get("/cody-ai", response_class=HTMLResponse)
def cody_ai_page(request: Request, plan_id: int | None = None, db: Session = Depends(get_db)):
    user = current_user(request, db)
    plan = db.get(CareerPlan, plan_id) if plan_id and user else None
    if plan and plan.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Career plan not found")
    profile = db.get(CareerProfile, user.id) if user else None
    course_ids = {product_id for stage in plan.stages for product_id in stage.get("course_ids", [])} if plan else set()
    plan_courses = {product.id: product for product in db.scalars(select(Product).where(Product.id.in_(course_ids)))} if course_ids else {}
    return templates.TemplateResponse(
        request,
        "cody_ai.html",
        page_context(request, db, question="", related_courses=[], profile=profile, plan=plan, plan_courses=plan_courses, error=None),
    )


@app.post("/cody-ai/ask", response_class=HTMLResponse)
def cody_ai_ask(
    request: Request,
    question: str = Form(min_length=2, max_length=500),
    _csrf: None = Depends(require_form_csrf),
    db: Session = Depends(get_db),
):
    products = list(db.scalars(select(Product).where(Product.is_active.is_(True))))
    by_id = {product.id: product for product in products}
    try:
        vector_ids = vector_store().search(question, limit=8)
    except RuntimeError:
        vector_ids = []
    ranked_ids = list(dict.fromkeys([*vector_ids, *lexical_rank(question, products, limit=8)]))[:8]
    related_courses = [by_id[product_id] for product_id in ranked_ids if product_id in by_id]
    if not related_courses:
        related_courses = sorted(products, key=lambda product: product.rating, reverse=True)[:6]
    user = current_user(request, db)
    profile = db.get(CareerProfile, user.id) if user else None
    return templates.TemplateResponse(
        request,
        "cody_ai.html",
        page_context(request, db, question=question, related_courses=related_courses, profile=profile, plan=None, plan_courses={}, error=None),
    )


@app.post("/cody-ai/career-path")
def create_career_path(
    request: Request,
    background_tasks: BackgroundTasks,
    experience: str = Form(min_length=2, max_length=2000),
    current_skills: str = Form(default="", max_length=1000),
    career_interests: str = Form(min_length=2, max_length=1000),
    target_role: str = Form(min_length=2, max_length=150),
    skill_level: str = Form(pattern="^(Beginner|Intermediate|Expert)$"),
    _csrf: None = Depends(require_form_csrf),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    skills = [skill.strip() for skill in current_skills.split(",") if skill.strip()]
    profile_data = {"experience": experience.strip(), "current_skills": skills, "career_interests": career_interests.strip(), "target_role": target_role.strip(), "skill_level": skill_level}
    products = list(db.scalars(select(Product).where(Product.is_active.is_(True))))
    retrieval_query = f"{target_role} {career_interests} {' '.join(skills)} {skill_level}"
    try:
        vector_ids = vector_store().search(retrieval_query, limit=15)
    except RuntimeError:
        vector_ids = []
    by_id = {product.id: product for product in products}
    candidate_ids = list(dict.fromkeys([*vector_ids, *lexical_rank(retrieval_query, products, limit=15)]))[:15]
    candidates = [by_id[product_id] for product_id in candidate_ids if product_id in by_id]
    if not candidates:
        candidates = sorted(products, key=lambda product: product.rating, reverse=True)[:12]
    catalogue = [{"id": product.id, "title": product.title, "description": product.description, "track": product.track, "level": product.level, "tags": product.tags, "rating": product.rating} for product in candidates]
    try:
        payload = mesh.career_plan(profile_data, catalogue)
    except (RuntimeError, ValueError) as error:
        profile = db.get(CareerProfile, user.id)
        return templates.TemplateResponse(request, "cody_ai.html", page_context(request, db, question="", related_courses=[], profile=profile, plan=None, plan_courses={}, error=str(error)), status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    valid_ids = {product.id for product in candidates}
    stages = []
    for stage in payload.stages:
        stage_data = stage.model_dump()
        stage_data["course_ids"] = [product_id for product_id in stage.course_ids if product_id in valid_ids]
        stages.append(stage_data)
    profile = db.get(CareerProfile, user.id) or CareerProfile(user_id=user.id, **profile_data)
    for key, value in profile_data.items():
        setattr(profile, key, value)
    db.add(profile)
    plan = CareerPlan(user_id=user.id, title=payload.title, summary=payload.summary, target_role=payload.target_role, estimated_months=payload.estimated_months, hero_message=payload.hero_message, stages=stages)
    db.add(plan)
    db.flush()
    enqueue_career_vector(db, plan)
    db.commit()
    background_tasks.add_task(scheduled_vector_sync)
    return RedirectResponse(f"/cody-ai?plan_id={plan.id}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/my-learning", response_class=HTMLResponse)
def my_learning(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    enrollments = list(
        db.scalars(
            select(Enrollment)
            .where(Enrollment.user_id == user.id)
            .order_by(Enrollment.updated_at.desc())
        )
    )
    recommendation = db.scalar(
        select(Recommendation)
        .where(Recommendation.user_id == user.id)
        .order_by(Recommendation.created_at.desc())
    )
    enrolled_ids = [enrollment.product_id for enrollment in enrollments]
    suggested_query = select(Product).where(Product.is_active.is_(True))
    if enrolled_ids:
        suggested_query = suggested_query.where(Product.id.not_in(enrolled_ids))
    suggested_products = list(
        db.scalars(suggested_query.order_by(Product.rating.desc()).limit(6))
    )
    fallback_recommendation_items = [
        {
            "product": product,
            "reason": "A highly rated catalogue course that complements your current learning.",
        }
        for product in suggested_products
    ]
    events = list(
        db.scalars(
            select(BehaviorEvent)
            .where(BehaviorEvent.user_id == user.id)
            .order_by(BehaviorEvent.occurred_at.desc())
            .limit(1000)
        )
    )
    activity_product_ids = {event.product_id for event in events if event.product_id}
    activity_products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_(activity_product_ids)))
    }
    return templates.TemplateResponse(
        request,
        "my_learning.html",
        page_context(
            request,
            db,
            enrollments=enrollments,
            recommendation=recommendation,
            fallback_recommendation_items=fallback_recommendation_items,
            activity=learning_activity(events, activity_products),
        ),
    )


@app.post("/products/{product_id}/start", dependencies=[Depends(require_form_csrf)])
def start_course(product_id: int, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = require_user(request, db)
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.user_id == user.id,
            Enrollment.product_id == product_id,
        )
    )
    if not enrollment:
        enrollment = Enrollment(user_id=user.id, product_id=product_id)
        db.add(enrollment)
        db.flush()
        enqueue_learning_vector(db, enrollment)
        db.commit()
        background_tasks.add_task(scheduled_vector_sync)
    return RedirectResponse("/my-learning", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "auth.html", page_context(request, db, mode="register", error=None)
    )


@app.post("/register")
def register(
    request: Request,
    email: str = Form(min_length=3, max_length=320),
    password: str = Form(min_length=8, max_length=128),
    _csrf: None = Depends(require_form_csrf),
    db: Session = Depends(get_db),
):
    user = User(email=email.strip().lower(), password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request,
            "auth.html",
            page_context(request, db, mode="register", error="That email is already registered."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "auth.html", page_context(request, db, mode="login", error=None)
    )


@app.post("/login")
def login(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    _csrf: None = Depends(require_form_csrf),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "auth.html",
            page_context(request, db, mode="login", error="Invalid email or password."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout", dependencies=[Depends(require_form_csrf)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/api/events")
def ingest_events(
    batch: EventBatchIn,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_header_csrf),
    db: Session = Depends(get_db),
):
    now = datetime.now(UTC)
    incoming = {event.event_id: event for event in batch.events}
    existing = set(db.scalars(select(BehaviorEvent.event_id).where(BehaviorEvent.user_id == user.id, BehaviorEvent.event_id.in_(incoming))))
    new_events = [event for event_id, event in incoming.items() if event_id not in existing]
    db.add_all(
        [
            BehaviorEvent(
                event_id=event.event_id,
                user_id=user.id,
                event_type=event.event_type,
                product_id=event.product_id,
                search_query=event.search_query,
                category=event.category,
                event_metadata=event.metadata,
                session_id=event.session_id,
                occurred_at=event.occurred_at or now,
            )
            for event in new_events
        ]
    )
    db.commit()
    duplicate_count = len(batch.events) - len(new_events)
    logfire.info("behavior events ingested", user_id=user.id, event_count=len(new_events), duplicate_count=duplicate_count)
    background_tasks.add_task(generate_for_user, user.id)
    return {"accepted": len(new_events)}


@app.get("/api/recommendations/latest")
def latest_recommendation(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    recommendation = db.scalar(
        select(Recommendation)
        .where(Recommendation.user_id == user.id)
        .order_by(Recommendation.created_at.desc())
    )
    return {
        "id": recommendation.id if recommendation else None,
        "created_at": recommendation.created_at.isoformat() if recommendation else None,
    }


@app.get("/admin/products", response_class=HTMLResponse)
def admin_products(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    products = list(db.scalars(select(Product).order_by(Product.created_at.desc())))
    return templates.TemplateResponse(
        request,
        "admin.html",
        page_context(request, db, products=products, error=None),
    )


@app.get("/admin/agent-runs", response_class=HTMLResponse)
def admin_agent_runs(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    selected_status = request.query_params.get("status", "all")
    if selected_status not in {"all", "running", "completed", "failed"}:
        selected_status = "all"
    query = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(200)
    if selected_status != "all":
        query = query.where(AgentRun.status == selected_status)
    runs = list(db.scalars(query))
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_({run.user_id for run in runs})))}
    rows = []
    for run in runs:
        duration = "—"
        if run.completed_at:
            seconds = max(0, (run.completed_at - run.started_at).total_seconds())
            duration = f"{seconds:.1f}s" if seconds < 60 else f"{seconds / 60:.1f}m"
        user = users.get(run.user_id)
        rows.append({"run": run, "email": user.email if user else f"User #{run.user_id}", "duration": duration})

    all_runs = list(db.scalars(select(AgentRun)))
    completed = sum(run.status == "completed" for run in all_runs)
    durations = [(run.completed_at - run.started_at).total_seconds() for run in all_runs if run.completed_at]
    metrics = {
        "total": len(all_runs),
        "success_rate": round(completed / len(all_runs) * 100, 1) if all_runs else 0,
        "failed": sum(run.status == "failed" for run in all_runs),
        "average_duration": f"{sum(durations) / len(durations):.1f}s" if durations else "—",
    }
    return templates.TemplateResponse(
        request,
        "agent_runs.html",
        page_context(request, db, rows=rows, metrics=metrics, selected_status=selected_status),
    )


@app.post("/admin/products")
def create_product(
    request: Request,
    title: str = Form(min_length=2, max_length=200),
    provider: str = Form(default="", max_length=150),
    track: str = Form(default="", max_length=50),
    level: str = Form(default="Beginner", max_length=30),
    description: str = Form(min_length=10),
    category: str = Form(min_length=2, max_length=100),
    price: float = Form(ge=0),
    currency: str = Form(default="INR", min_length=3, max_length=3),
    rating: float = Form(default=0, ge=0, le=5),
    tags: str = Form(default=""),
    syllabus: str = Form(default=""),
    image_url: str = Form(default="", max_length=500),
    is_active: bool = Form(default=False),
    _csrf: None = Depends(require_form_csrf),
    db: Session = Depends(get_db),
):
    require_admin(request, db)
    product = Product(
        title=title.strip(),
        provider=provider.strip(),
        track=track.strip().lower(),
        level=level.strip().title(),
        description=description.strip(),
        category=category.strip(),
        price=price,
        currency=currency.strip().upper(),
        rating=rating,
        tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
        syllabus=syllabus.strip(),
        image_url=image_url.strip(),
        is_active=is_active,
    )
    db.add(product)
    db.flush()
    enqueue_vector_operation(db, product, "upsert" if is_active else "delete")
    db.commit()
    return RedirectResponse("/admin/products", status_code=status.HTTP_303_SEE_OTHER)


@app.post(
    "/admin/products/{product_id}/sync", dependencies=[Depends(require_form_csrf)]
)
def sync_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    enqueue_vector_operation(db, product, "upsert")
    db.commit()
    return RedirectResponse("/admin/products", status_code=status.HTTP_303_SEE_OTHER)


@app.post(
    "/admin/products/{product_id}/delete", dependencies=[Depends(require_form_csrf)]
)
def delete_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    product.is_active = False
    enqueue_vector_operation(db, product, "delete")
    db.commit()
    return RedirectResponse("/admin/products", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin/products/{product_id}/edit", response_class=HTMLResponse)
def edit_product_page(product_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return templates.TemplateResponse(request, "edit_product.html", page_context(request, db, product=product))


@app.post("/admin/products/{product_id}/edit")
def edit_product(
    product_id: int,
    request: Request,
    title: str = Form(min_length=2, max_length=200),
    provider: str = Form(default="", max_length=150),
    track: str = Form(default="", max_length=50),
    level: str = Form(default="", max_length=30),
    category: str = Form(min_length=2, max_length=100),
    price: float = Form(ge=0),
    currency: str = Form(min_length=3, max_length=3),
    rating: float = Form(default=0, ge=0, le=5),
    tags: str = Form(default=""),
    syllabus: str = Form(default=""),
    description: str = Form(min_length=10),
    image_url: str = Form(default="", max_length=500),
    is_active: bool = Form(default=False),
    _csrf: None = Depends(require_form_csrf),
    db: Session = Depends(get_db),
):
    require_admin(request, db)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    product.title = title.strip()
    product.provider = provider.strip()
    product.track = track.strip().lower()
    product.level = level.strip().title()
    product.category = category.strip()
    product.price = price
    product.currency = currency.strip().upper()
    product.rating = rating
    product.tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    product.syllabus = syllabus.strip()
    product.description = description.strip()
    product.image_url = image_url.strip()
    product.is_active = is_active
    enqueue_vector_operation(db, product, "upsert" if is_active else "delete")
    db.commit()
    return RedirectResponse("/admin/products", status_code=status.HTTP_303_SEE_OTHER)
