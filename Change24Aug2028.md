# SmartReco Recommendation Changes

**Date:** 24 August 2028  
**Repository:** [rkumar670/SmartReco](https://github.com/rkumar670/SmartReco)  
**Branch:** main

## Purpose

This document records the recommendation improvements implemented and the remaining roadmap for making SmartReco more accurate, explainable, measurable, and production-ready.

## Implemented changes

### Behavior signatures detect new events

Recommendation behavior versions now include each event's client event ID and timestamp. A new event with the same type and payload as an older event can therefore trigger a new recommendation.

### Enrolled products are excluded

Products with an existing learner enrollment are removed before candidate retrieval. This prevents recommending courses the learner has already started or completed.

### Vector results are limited to eligible products

Semantic search results are filtered against the eligible catalog before reciprocal-rank fusion, so ineligible products cannot re-enter through vector search.

### Deterministic cold-start ordering

Product ID is now used as a final tie-breaker after rating and price, making identical catalog data produce stable ordering.

### Regression tests

Tests cover different event IDs producing different signatures and removing enrolled products from the candidate pool.

## Recommended next phases

### Phase 1: Event quality and processing

- Validate that product events reference valid products.
- Require meaningful search queries and bounded time-spent values.
- Normalize search terms before profile scoring.
- Reject impossible timestamps and limit events per user, session, and time window.
- Keep failed-generation events unprocessed so they can be retried.

### Phase 2: Stronger learner profiles

- Store separate weights for tracks, categories, skills, levels, search terms, and providers.
- Give clicks and enrollments more weight than passive views.
- Add negative signals for dismissals, skips, and very short visits.
- Apply different recency decay by signal type.
- Store profile confidence and versioned profile history.

### Phase 3: Better candidate generation

Combine semantic vectors, lexical search, preferred tracks, popular courses, recent courses, and prerequisite or next-step courses. Filter by activity status, enrollment state, level, price, currency, language, provider, and category.

### Phase 4: Deterministic reranking

Use an application-controlled score combining relevance, profile match, level fit, quality, novelty, freshness, and price fit. Limit repeated tracks and providers while keeping relevance primary.

### Phase 5: Use the LLM for explanation

The application should select and order final products deterministically. The LLM should generate only the title, narrative, and reasons for those products. Validate IDs, item count, reason length, duplicate items, and unsupported claims before persistence.

### Phase 6: Measurement and experimentation

Track impressions, clicks, enrollments, completion, dismissals, catalog coverage, diversity, novelty, and cold-start performance. Store algorithm version, profile version, retrieval sources, candidate count, scores, and experiment variant.

## Production hardening still required

- Replace default development credentials with required deployment secrets.
- Require a strong non-default session secret outside development.
- Add atomic claim or lease handling to vector outbox jobs.
- Prevent concurrent recommendation generation for the same learner.
- Add a uniqueness constraint for each learner and behavior version.
- Move scheduled work to a dedicated durable worker for multi-instance deployments.
- Use shared PostgreSQL and vector storage in production instead of local SQLite and Chroma persistence.
- Add database, vector-store, scheduler, and Mesh checks to the health endpoint.

## Relevant commits

- [Improve recommendation candidate eligibility and signatures](https://github.com/rkumar670/SmartReco/commit/dd57e8f2def48e282562d55886dc7e8e060816f8)
- [Add recommendation regression tests](https://github.com/rkumar670/SmartReco/commit/18f990526796b23e059d11faf9260accc88d5f46)
- [Fix recommendation patch formatting](https://github.com/rkumar670/SmartReco/commit/2bfdfec9caac92ed3c8004226640d9251457dd89)
