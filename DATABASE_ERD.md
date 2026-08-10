# SmartReco database ER diagram

```mermaid
erDiagram
    USERS ||--o{ BEHAVIOR_EVENTS : generates
    USERS ||--o{ RECOMMENDATIONS : receives
    PRODUCTS o|--o{ BEHAVIOR_EVENTS : referenced_by
    RECOMMENDATIONS ||--|{ RECOMMENDATION_ITEMS : contains
    PRODUCTS ||--o{ RECOMMENDATION_ITEMS : recommended_as

    USERS {
        int id PK
        string email UK
        string password_hash
        string role
        datetime created_at
    }

    PRODUCTS {
        int id PK
        string title
        text description
        string category
        float price
        string image_url
        boolean is_active
        string vector_status
        datetime created_at
        datetime updated_at
    }

    BEHAVIOR_EVENTS {
        int id PK
        int user_id FK
        string event_type
        int product_id FK "nullable"
        string search_query "nullable"
        string category "nullable"
        json event_metadata
        string session_id
        datetime occurred_at
        datetime processed_at "nullable"
    }

    RECOMMENDATIONS {
        int id PK
        int user_id FK
        string title
        text narrative
        text profile_summary
        string behavior_version
        datetime created_at
    }

    RECOMMENDATION_ITEMS {
        int id PK
        int recommendation_id FK
        int product_id FK
        text reason
        int rank
    }
```

The diagram covers the application database (`data/smartreco.db`). Chroma's SQLite tables
are internal vector-store implementation details and are intentionally excluded.
