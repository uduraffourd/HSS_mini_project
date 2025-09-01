-- Stations météo
CREATE TABLE IF NOT EXISTS weather_stations (
  id                     BIGSERIAL PRIMARY KEY,
  weather_station_code   TEXT NOT NULL UNIQUE,
  weather_station_name   TEXT NOT NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Centrales hydro
CREATE TABLE IF NOT EXISTS hydropower_plants (
  id                 BIGSERIAL PRIMARY KEY,
  hpp_code           TEXT NOT NULL UNIQUE,
  hpp_name           TEXT NOT NULL,
  weather_station_id BIGINT REFERENCES weather_stations(id) ON DELETE SET NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Séries de pluie (6 min)
CREATE TABLE IF NOT EXISTS rainfall_6min (
  id          BIGSERIAL PRIMARY KEY,
  station_id  BIGINT NOT NULL REFERENCES weather_stations(id) ON DELETE CASCADE,
  ts_utc      TIMESTAMPTZ NOT NULL,
  rainfall_mm DOUBLE PRECISION NOT NULL CHECK (rainfall_mm >= 0),
  CONSTRAINT uniq_station_ts UNIQUE (station_id, ts_utc),
  CONSTRAINT chk_6min_aligned CHECK ( (EXTRACT(EPOCH FROM ts_utc)::INT % 360) = 0 )
);

CREATE INDEX IF NOT EXISTS idx_rain_station_ts ON rainfall_6min (station_id, ts_utc);
CREATE INDEX IF NOT EXISTS idx_rain_ts         ON rainfall_6min (ts_utc);