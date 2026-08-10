from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_event_id_column(engine: Engine) -> None:
    if engine.dialect.name != "sqlite" or not inspect(engine).has_table("behavior_events"):
        return
    columns = {column["name"] for column in inspect(engine).get_columns("behavior_events")}
    with engine.begin() as connection:
        if "event_id" not in columns:
            connection.execute(text("ALTER TABLE behavior_events ADD COLUMN event_id VARCHAR(36)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_behavior_user_event ON behavior_events (user_id, event_id)"))
