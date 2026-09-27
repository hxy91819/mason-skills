from src.shared import load_one, present


def get_user(store, tenant, user_id):
    row = load_one(store, tenant, user_id)
    return present(row) if row is not None else None
