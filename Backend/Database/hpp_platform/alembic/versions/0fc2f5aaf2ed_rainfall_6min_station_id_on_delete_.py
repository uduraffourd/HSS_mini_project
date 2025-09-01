from alembic import op

# revision identifiers, used by Alembic.
revision = "0fc2f5aaf2ed"        # <-- laissé par Alembic
down_revision = "c391d4ad47bf"   # <-- idem

def upgrade():
    # 1) supprimer l'ancienne contrainte (nom à adapter si besoin)
    op.drop_constraint(
        "rainfall_6min_station_id_fkey",  # <-- nom courant par défaut Postgres
        "rainfall_6min",
        type_="foreignkey",
    )
    # 2) recréer avec ON DELETE CASCADE
    op.create_foreign_key(
        "rainfall_6min_station_id_fkey",
        source_table="rainfall_6min",
        referent_table="weather_stations",
        local_cols=["station_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

def downgrade():
    # revenir à une FK sans CASCADE (comportement antérieur)
    op.drop_constraint(
        "rainfall_6min_station_id_fkey",
        "rainfall_6min",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "rainfall_6min_station_id_fkey",
        "rainfall_6min",
        "weather_stations",
        ["station_id"],
        ["id"],
        ondelete=None,
    )