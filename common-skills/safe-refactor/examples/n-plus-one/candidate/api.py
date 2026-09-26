from src.batch import load_batch
from src.shared import present


def list_users(store, tenant, ids):
    return [present(row) for row in load_batch(store, tenant, ids)]
