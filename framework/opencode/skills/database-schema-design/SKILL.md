---
name: database-schema-design
description: Design database schema changes for features involving persistent data. Covers existing schema discovery, entity modeling, relationships, constraints, indexes, migration strategy, rollback, and query performance implications. Use when a feature introduces or modifies database tables, columns, indexes, or relationships.
---

# Database Schema Design

Schema changes are permanent. Design them with the same rigor as API contracts.

## Mandatory sequence

```
Existing schema discovery
        ↓
Existing data and access patterns
        ↓
Entities
        ↓
Relationships
        ↓
Constraints
        ↓
Indexes
        ↓
Migration strategy
        ↓
Existing-data compatibility
        ↓
Rollback strategy
        ↓
Query performance implications
        ↓
Validation
```

## Rule: investigate before designing

Before proposing any schema change, the agent MUST:

1. **Discover existing tables** — what tables exist today?
2. **Understand data volume** — how much data is in each affected table?
3. **Map access patterns** — which queries touch this table?
4. **Identify existing indexes** — what indexes already exist?
5. **Check migration constraints** — could migration lock the table?
6. **Assess backfill needs** — is backfill required? How long will it take?

## Required output

```yaml
database_design:
  requirement_id: REQ-XXX
  existing_schema:
    affected_tables:
      - table: [table name]
        current_columns: [list]
        current_indexes: [list]
        row_count_estimate: [approximate]
        access_patterns:
          - query: [what queries touch this table]
            frequency: [high | medium | low]
            performance_sensitivity: [high | medium | low]
  new_entities:
    - entity: [entity name]
      table: [table name]
      columns:
        - name: [column]
          type: [type]
          nullable: [true | false]
          default: [value]
          description: [what it stores]
      primary_key: [column(s)]
      description: [what this entity represents]
  modified_entities:
    - entity: [entity name]
      table: [table name]
      changes:
        - type: [add_column | modify_column | drop_column]
          column: [column name]
          details: [what changes]
  relationships:
    - from: [table.column]
      to: [table.column]
      type: [one-to-one | one-to-many | many-to-many]
      on_delete: [cascade | restrict | set-null | no-action]
  constraints:
    - type: [unique | check | foreign_key]
      columns: [column(s)]
      definition: [constraint definition]
  indexes:
    - name: [index name]
      columns: [column(s)]
      type: [btree | hash | gin | gist]
      purpose: [what query this optimizes]
  migration:
    strategy: [create | alter | rename]
    backward_compatible: [true | false]
    lock_risk: [none | low | medium | high]
    backfill_required: [true | false]
    backfill_strategy: [description if required]
  rollback:
    strategy: [reverse_migration | point_in_time | manual]
    data_loss_risk: [none | low | medium | high]
    estimated_time: [time estimate]
  query_performance:
    affected_queries:
      - query: [query pattern]
        impact: [improved | unchanged | degraded]
        mitigation: [what to do if degraded]
  validation:
    - [how to prove the schema works]
```

## Migration safety checklist

- [ ] Migration can be applied without locking the table (or lock is acceptable)
- [ ] Backward compatible: old code works with new schema
- [ ] Rollback plan exists and has been considered
- [ ] Backfill strategy defined if existing data needs migration
- [ ] No data loss on rollback
- [ ] Index creation is non-blocking (or scheduled during low traffic)
- [ ] Column defaults do not cause unintended behavior

## Integration with other skills

- Requires: `software-architecture-design` output (system context)
- Requires: `technical-validation` when data compatibility assumptions exist
- Feeds: `implementer` (schema design → migration code)
- Coordinates with: `api-design` (API depends on data model)
- Coordinates with: `performance-testing` (query performance validation)
