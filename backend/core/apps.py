from django.apps import AppConfig
from django.db.backends.signals import connection_created


def sqlite_setup(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        connection.cursor().execute("PRAGMA journal_mode=WAL")


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        connection_created.connect(sqlite_setup)
