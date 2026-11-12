from django.db import migrations


def forwards(apps, schema_editor):
    """
    Close the gaps left by 0002:
    - SQLite: 0002 only blocked UPDATE; add a matching DELETE trigger.
    - PostgreSQL: REVOKE does nothing when the app role owns the table (and 0002
      swallowed any error), so enforce with triggers that apply to every role.
    """
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        schema_editor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_auditlog_delete
            BEFORE DELETE ON audit_auditlog
            BEGIN
                SELECT RAISE(ABORT, 'AuditLog table is insert-only: DELETE disallowed at database level');
            END;
            """
        )
    elif vendor == "postgresql":
        schema_editor.execute(
            """
            CREATE OR REPLACE FUNCTION audit_auditlog_insert_only() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'AuditLog table is insert-only: % disallowed at database level', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        schema_editor.execute(
            """
            DROP TRIGGER IF EXISTS prevent_auditlog_mutation ON audit_auditlog;
            CREATE TRIGGER prevent_auditlog_mutation
                BEFORE UPDATE OR DELETE ON audit_auditlog
                FOR EACH ROW EXECUTE FUNCTION audit_auditlog_insert_only();
            DROP TRIGGER IF EXISTS prevent_auditlog_truncate ON audit_auditlog;
            CREATE TRIGGER prevent_auditlog_truncate
                BEFORE TRUNCATE ON audit_auditlog
                FOR EACH STATEMENT EXECUTE FUNCTION audit_auditlog_insert_only();
            """
        )


def backwards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        schema_editor.execute("DROP TRIGGER IF EXISTS prevent_auditlog_delete;")
    elif vendor == "postgresql":
        schema_editor.execute(
            """
            DROP TRIGGER IF EXISTS prevent_auditlog_mutation ON audit_auditlog;
            DROP TRIGGER IF EXISTS prevent_auditlog_truncate ON audit_auditlog;
            DROP FUNCTION IF EXISTS audit_auditlog_insert_only();
            """
        )


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_enforce_insert_only"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
