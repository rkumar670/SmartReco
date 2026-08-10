from app.database import SessionLocal
from app.models import Product, VectorOutbox
from app.recommendations import diversify, lexical_rank, rrf
from app.vector_outbox import enqueue_vector_operation, process_vector_outbox


class FakeVectors:
    def __init__(self):
        self.upserted = []

    def upsert(self, product):
        self.upserted.append(product.id)

    def delete(self, product_id):
        pass


def product(title, track, rating=4.5):
    return Product(title=title, description=title, category=track, track=track, price=0, rating=rating)


def test_hybrid_ranking_and_diversity():
    products = [product("Python Data Analysis", "data"), product("Python Web API", "web-dev"), product("Advanced SQL", "data")]
    assert lexical_rank("python data", products)[0] == products[0].id
    fused = rrf([1, 2], [2, 3])
    assert fused[0] == 2
    mapped = {index + 1: item for index, item in enumerate(products)}
    assert diversify([1, 3, 2], mapped, 2) == [1, 2]


def test_vector_outbox_marks_product_synced():
    with SessionLocal() as db:
        item = product("Queued Product", "data")
        db.add(item)
        db.flush()
        enqueue_vector_operation(db, item, "upsert")
        db.commit()
        vectors = FakeVectors()
        assert process_vector_outbox(db, vectors) == 1
        assert db.get(Product, item.id).vector_status == "synced"
        assert db.query(VectorOutbox).one().status == "completed"
