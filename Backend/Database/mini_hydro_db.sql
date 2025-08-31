-- Table des centrales hydro
CREATE TABLE IF NOT EXISTS hydropower_plants (
  id                  BIGSERIAL PRIMARY KEY,
  hpp_id            TEXT NOT NULL UNIQUE,
  hpp_name                TEXT NOT NULL,
  weather_station_id  TEXT REFERENCES weather_stations(station_id) ON DELETE SET NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table des stations météo
CREATE TABLE IF NOT EXISTS weather_stations (
  weather_station_id   TEXT PRIMARY KEY,        -- identifiant officiel (ex: "FR_12345")
  weather_station_name         TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table des séries de pluie
CREATE TABLE IF NOT EXISTS rainfall_6min (
  id                  BIGSERIAL PRIMARY KEY,
  weather_station_id          TEXT NOT NULL REFERENCES weather_stations(station_id) ON DELETE CASCADE,
  ts_utc              TIMESTAMPTZ NOT NULL,
  rainfall_mm         DOUBLE PRECISION NOT NULL CHECK (rainfall_mm >= 0),
  CONSTRAINT uniq_station_ts UNIQUE (station_id, ts_utc),
  CONSTRAINT chk_6min_aligned CHECK ( (EXTRACT(EPOCH FROM ts_utc)::INT % 360) = 0 )
);

CREATE INDEX IF NOT EXISTS idx_rain_station_ts ON rainfall_6min (station_id, ts_utc);
CREATE INDEX IF NOT EXISTS idx_rain_ts         ON rainfall_6min (ts_utc);