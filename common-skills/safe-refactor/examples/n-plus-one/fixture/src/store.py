import sqlite3


class Store:
    """Small real SQLite fixture; IDs are globally unique in this example."""
    def __init__(self, rows):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("create table users (id integer primary key, tenant text, name text)")
        self.db.executemany("insert into users values (?, ?, ?)", rows)
        self.selects = 0
        self.db.set_trace_callback(self._trace)

    def _trace(self, statement):
        if statement.lstrip().upper().startswith("SELECT"):
            self.selects += 1

    def one(self, user_id):
        row = self.db.execute("select id, tenant, name from users where id = ?", (user_id,)).fetchone()
        return dict(row) if row is not None else None

    def many(self, ids):
        if not ids:
            return {}
        marks = ",".join("?" for _ in ids)
        rows = self.db.execute("select id, tenant, name from users where id in (" + marks + ")", ids)
        return {row["id"]: dict(row) for row in rows}

    def close(self):
        self.db.close()
