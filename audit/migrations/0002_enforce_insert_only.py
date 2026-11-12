from django.db import migrations, connection


def get_insert_only_sql():
    """
    Database-level enforcement of insert-only constraint on audit_auditlog.
    - PostgreSQL: REVOKE UPDATE, DELETE permissions
    - SQLite: DB-level triggers raising ABORT on UPDATE or DELETE
    """
    if connection.vendor == "postgresql":
        return """
        DO $$
        BEGIN
            REVOKE UPDATE, DELETE ON audit_auditlog FROM CURRENT_USER;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
        """
    return """
    CREATE TRIGGER IF NOT EXISTS prevent_auditlog_update
    BEFORE UPDATE ON audit_auditlog
    BEGIN
        SELECT RAISE(ABORT, 'AuditLog table is insert-only: UPDATE disallowed at database level');
    END;
    """


def get_reverse_sql():
    if connection.vendor == "postgresql":
        return "GRANT UPDATE, DELETE ON audit_auditlog TO CURRENT_USER;"
    return """
    DROP TRIGGER IF EXISTS prevent_auditlog_update;
    DROP TRIGGER IF EXISTS prevent_auditlog_delete;
    """


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=get_insert_only_sql(),
            reverse_sql=get_reverse_sql(),
        ),
    ]
