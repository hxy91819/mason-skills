def visible(row, tenant):
    return row is not None and row["tenant"] == tenant


def load_one(store, tenant, user_id):
    row = store.one(user_id)
    return row if visible(row, tenant) else None


def present(row):
    return {"id": row["id"], "name": row["name"]}
