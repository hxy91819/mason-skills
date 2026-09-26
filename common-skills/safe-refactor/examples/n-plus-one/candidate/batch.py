from src.shared import visible

BATCH_SIZE = 100


def load_batch(store, tenant, ids):
    # Each batch retains input ordering and duplicates; authorization is unchanged.
    result = []
    for offset in range(0, len(ids), BATCH_SIZE):
        batch = ids[offset:offset + BATCH_SIZE]
        rows = store.many(batch)
        result.extend(rows[user_id] for user_id in batch if visible(rows.get(user_id), tenant))
    return result
