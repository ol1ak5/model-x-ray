import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver


def sqlite_checkpointer(path: str) -> SqliteSaver:
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))
