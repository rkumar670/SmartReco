import logfire
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CareerPlan, CareerVectorOutbox, Enrollment, LearningVectorOutbox, Product, User, VectorOutbox, utcnow
from app.vectors import ProductVectors


def enqueue_vector_operation(db: Session, product: Product, operation: str) -> None:
    product.vector_status = "pending"
    db.add(VectorOutbox(product_id=product.id, operation=operation))


def enqueue_learning_vector(db: Session, enrollment: Enrollment) -> None:
    enrollment.vector_status = "pending"
    db.add(LearningVectorOutbox(enrollment_id=enrollment.id))


def enqueue_career_vector(db: Session, plan: CareerPlan) -> None:
    plan.vector_status = "pending"
    db.add(CareerVectorOutbox(career_plan_id=plan.id))


def process_vector_outbox(db: Session, vectors: ProductVectors, limit: int = 50) -> int:
    jobs = list(db.scalars(select(VectorOutbox).where(VectorOutbox.status == "pending").order_by(VectorOutbox.id).limit(limit)))
    completed = 0
    for job in jobs:
        product = db.get(Product, job.product_id)
        job.attempts += 1
        try:
            if job.operation == "delete" or not product or not product.is_active:
                vectors.delete(job.product_id)
                if product:
                    product.vector_status = "deleted"
            else:
                vectors.upsert(product)
                product.vector_status = "synced"
            job.status = "completed"
            job.processed_at = utcnow()
            completed += 1
        except (RuntimeError, ValueError) as error:
            job.error = str(error)
            if job.attempts >= 3:
                job.status = "failed"
                if product:
                    product.vector_status = "failed"
            logfire.warn("vector outbox failed", job_id=job.id, reason=str(error))
        db.commit()
    learning_jobs = list(db.scalars(select(LearningVectorOutbox).where(LearningVectorOutbox.status == "pending").order_by(LearningVectorOutbox.id).limit(limit)))
    for job in learning_jobs:
        enrollment = db.get(Enrollment, job.enrollment_id)
        job.attempts += 1
        try:
            if not enrollment:
                job.status = "completed"
            else:
                user = db.get(User, enrollment.user_id)
                product = db.get(Product, enrollment.product_id)
                if not user or not product:
                    raise ValueError("Enrollment references missing data")
                vectors.upsert_enrollment(enrollment, user, product)
                enrollment.vector_status = "synced"
                job.status = "completed"
            job.processed_at = utcnow()
            completed += 1
        except (RuntimeError, ValueError) as error:
            job.error = str(error)
            if job.attempts >= 3:
                job.status = "failed"
                if enrollment:
                    enrollment.vector_status = "failed"
            logfire.warn("learning vector outbox failed", job_id=job.id, reason=str(error))
        db.commit()
    career_jobs = list(db.scalars(select(CareerVectorOutbox).where(CareerVectorOutbox.status == "pending").order_by(CareerVectorOutbox.id).limit(limit)))
    for job in career_jobs:
        plan = db.get(CareerPlan, job.career_plan_id)
        job.attempts += 1
        try:
            if not plan:
                job.status = "completed"
            else:
                user = db.get(User, plan.user_id)
                if not user:
                    raise ValueError("Career plan references a missing user")
                vectors.upsert_career_plan(plan, user)
                plan.vector_status = "synced"
                job.status = "completed"
            job.processed_at = utcnow()
            completed += 1
        except (RuntimeError, ValueError) as error:
            job.error = str(error)
            if job.attempts >= 3:
                job.status = "failed"
                if plan:
                    plan.vector_status = "failed"
            logfire.warn("career vector outbox failed", job_id=job.id, reason=str(error))
        db.commit()
    return completed
