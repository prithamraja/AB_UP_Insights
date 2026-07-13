# Critical Findings 1 and 2

This document explains two critical correctness issues in the Ask module.

## 1. Repeated SQL parameter slots are bound only once

### Issue

Some templates use the same entity in multiple SQL placeholders. T91 filters both its `enrolled` and `treated` subqueries by district:

```sql
WHERE h.home_district_code = ?  -- enrolled
...
WHERE h.home_district_code = ?  -- treated
```

Its metadata correctly declares two positions:

```python
"param_slots": [
    {"name": "district", "position": 1},
    {"name": "district", "position": 2},
]
```

For a question about Lucknow, entity extraction correctly produces one logical value:

```python
district = "Lucknow"
```

But SQL needs one value per placeholder:

```python
["Lucknow", "Lucknow"]
```

The normal route in `router.py` builds parameters from `validated_entities`. Because there is only one logical district entity, it supplies only `["Lucknow"]`. The database receives two placeholders but one value and rejects the query. T99 is a more severe example: it has five district placeholders but still receives one value.

### Root cause and correction

A logical entity is not the same as a SQL parameter position. Extraction should produce one validated district; binding must copy it into every declared district position.

Build a lookup of validated values, then iterate through every `param_slot` in positional order:

```python
params_by_name = {
    entity.slot_name: entity.resolved_value
    for entity in validated_entities
}
param_values = [
    params_by_name[slot["name"]]
    for slot in sorted(param_slots, key=lambda slot: slot["position"])
]
```

The requery path already follows this slot-oriented approach. Normal execution and requery should ideally use one shared binding helper.

### Impact and tests

Affected templates deterministically fail despite correct routing and entity extraction. Tests should verify that T91 binds two district values, T99 binds five, and both execution paths behave identically.

---

## 2. Operations are not bound to the table whose toolbar was clicked

### Issue

A toolbar appears under a particular result table, but the frontend calls:

```typescript
runOperation(sessionId, args)
```

It does not send that table's backend `result_set.id`. The backend can therefore only interpret the request as "run this operation on whichever table is currently active in the session."

The UI has two unrelated IDs:

- `message.id` identifies a frontend chat message.
- `message.context_frame.result_set.id` identifies the backend result table.

`ChatArea.tsx` calls the latest catalog message's `message.id` `activeResultId`. Despite the name, it is not a result-set ID and is not matched against `currentFrame.result_set.id`.

### Failure scenario

1. Question A produces Table A.
2. Question B produces Table B.
3. The user selects **Back**, so the backend restores Table A.
4. The transcript still treats Table B as the latest catalog result and shows its toolbar.
5. The user clicks **Sum** under Table B.
6. No Table B result-set ID is sent.
7. The backend sums its current table: Table A.

The answer can look valid while being calculated from a different table than the UI indicated.

### Why the guard is insufficient

The API function and backend model support an optional `result_set_id`, but `Index.tsx` does not pass it, so the guard is skipped in the normal UI flow.

When an ID is supplied, the endpoint checks it only after `_execute_operation()`. A stale comparison can therefore perform an unnecessary database requery before being rejected.

### Correction

Pass the clicked message's result-set ID through the complete flow:

```typescript
runOperation(
  sessionId,
  args,
  message.context_frame?.result_set.id
)
```

The backend should compare this ID with the current frame before performing any calculation or requery. Toolbar-driven requests should preferably require the ID.

The UI should enable a toolbar only when its message's `context_frame.result_set.id` equals `currentFrame.result_set.id`; comparing frontend message IDs is insufficient.

### Impact and tests

This is a silent-correctness risk: an operation may return plausible numbers for the wrong table. Tests should verify that the clicked ID is sent, stale IDs return `409` before execution, going back moves the active toolbar, and resetting context disables old toolbars.

---

## Short version

- **Finding 1:** SQL may require the same entity several times, but normal routing supplies it once.
- **Finding 2:** The UI associates an operation with one table, but the request operates on the session's current table without identifying the clicked table.
