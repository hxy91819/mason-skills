from src.shared import load_one, present


def list_users(store, tenant, ids):
    result = []
    for user_id in ids:
        row = load_one(store, tenant, user_id)
        if row is not None:
            result.append(present(row))
    return result
