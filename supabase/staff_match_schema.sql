-- BAD360.ai — Staff Match (modulo BarmanMatch integrato) — Schema Supabase
-- Esegui nel SQL Editor del progetto Supabase di BAD360

-- ─── WORKER PROFILES ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS worker_profiles (
    id                      UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name               TEXT NOT NULL,
    email                   TEXT NOT NULL,
    phone                   TEXT,
    city                    TEXT NOT NULL,
    roles                   TEXT[] NOT NULL DEFAULT '{}',
    skills                  TEXT[] DEFAULT '{}',
    certifications          TEXT[] DEFAULT '{}',
    years_experience        INTEGER DEFAULT 0,
    bio                     TEXT,
    hourly_rate_min         NUMERIC(8,2),
    -- Stats denormalizzate per query veloci
    rating_avg              NUMERIC(3,2) DEFAULT 5.0,
    rating_count            INTEGER DEFAULT 0,
    completion_rate         NUMERIC(5,2) DEFAULT 100.0,
    no_show_count           INTEGER DEFAULT 0,
    total_shifts_completed  INTEGER DEFAULT 0,
    avg_response_time_mins  INTEGER DEFAULT 60,
    -- Badge
    badge_top_rated         BOOLEAN DEFAULT FALSE,
    badge_no_show_zero      BOOLEAN DEFAULT TRUE,
    badge_fast_responder    BOOLEAN DEFAULT FALSE,
    -- Stato
    is_verified             BOOLEAN DEFAULT FALSE,
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ─── VENUE PROFILES ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS venue_profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    phone       TEXT,
    city        TEXT NOT NULL,
    venue_type  TEXT NOT NULL CHECK (venue_type IN ('hotel','ristorante','resort','catering','event_venue','bar','altro')),
    address     TEXT,
    description TEXT,
    plan        TEXT DEFAULT 'starter' CHECK (plan IN ('starter','pro','business','enterprise')),
    is_verified BOOLEAN DEFAULT FALSE,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ─── SHIFTS (TURNI) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shifts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id        UUID NOT NULL REFERENCES venue_profiles(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    date            DATE NOT NULL,
    start_time      TIME NOT NULL,
    end_time        TIME NOT NULL,
    hourly_rate     NUMERIC(8,2) NOT NULL,
    city            TEXT NOT NULL,
    requirements    TEXT[] DEFAULT '{}',
    description     TEXT,
    dress_code      TEXT,
    spots           INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'open' CHECK (status IN ('open','filled','cancelled','completed')),
    is_urgent       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── SHIFT APPLICATIONS ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shift_applications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id            UUID NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    worker_id           UUID NOT NULL REFERENCES worker_profiles(id) ON DELETE CASCADE,
    status              TEXT DEFAULT 'pending' CHECK (status IN ('pending','confirmed','rejected','completed','no_show','withdrawn')),
    match_score         NUMERIC(5,2),
    applied_at          TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at        TIMESTAMPTZ,
    contract_accepted   BOOLEAN DEFAULT FALSE,
    contract_accepted_at TIMESTAMPTZ,
    UNIQUE(shift_id, worker_id)
);

-- ─── RATINGS ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ratings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id            UUID NOT NULL REFERENCES shifts(id),
    application_id      UUID NOT NULL REFERENCES shift_applications(id),
    rater_type          TEXT NOT NULL CHECK (rater_type IN ('venue','worker')),
    rater_id            UUID NOT NULL,
    ratee_id            UUID NOT NULL,
    score               INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment             TEXT,
    -- Dimensioni per venue→worker
    punctuality         INTEGER CHECK (punctuality BETWEEN 1 AND 5),
    professionalism     INTEGER CHECK (professionalism BETWEEN 1 AND 5),
    skill_level         INTEGER CHECK (skill_level BETWEEN 1 AND 5),
    -- Dimensioni per worker→venue
    work_environment    INTEGER CHECK (work_environment BETWEEN 1 AND 5),
    payment_punctuality INTEGER CHECK (payment_punctuality BETWEEN 1 AND 5),
    is_published        BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(application_id, rater_type)
);

-- ─── VENUE FAVORITES ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS venue_favorites (
    venue_id    UUID NOT NULL REFERENCES venue_profiles(id) ON DELETE CASCADE,
    worker_id   UUID NOT NULL REFERENCES worker_profiles(id) ON DELETE CASCADE,
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (venue_id, worker_id)
);

-- ─── INDEXES ────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_shifts_open          ON shifts(city, role, date) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_shifts_venue         ON shifts(venue_id);
CREATE INDEX IF NOT EXISTS idx_apps_worker          ON shift_applications(worker_id);
CREATE INDEX IF NOT EXISTS idx_apps_shift           ON shift_applications(shift_id);
CREATE INDEX IF NOT EXISTS idx_ratings_ratee        ON ratings(ratee_id);
CREATE INDEX IF NOT EXISTS idx_ratings_application  ON ratings(application_id);

-- ─── UPDATED_AT TRIGGER ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_worker_updated  BEFORE UPDATE ON worker_profiles  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_venue_updated   BEFORE UPDATE ON venue_profiles   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_shift_updated   BEFORE UPDATE ON shifts           FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─── ROW LEVEL SECURITY ─────────────────────────────────────────
ALTER TABLE worker_profiles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE venue_profiles   ENABLE ROW LEVEL SECURITY;
ALTER TABLE shifts            ENABLE ROW LEVEL SECURITY;
ALTER TABLE shift_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE ratings           ENABLE ROW LEVEL SECURITY;
ALTER TABLE venue_favorites   ENABLE ROW LEVEL SECURITY;

-- Worker può leggere il proprio profilo e aggiornarlo
CREATE POLICY "worker_self" ON worker_profiles
    FOR ALL USING (auth.uid() = id);
-- Chiunque autenticato può vedere i profili worker (per matching)
CREATE POLICY "worker_read_all" ON worker_profiles
    FOR SELECT USING (auth.role() = 'authenticated');

-- Venue può leggere il proprio profilo
CREATE POLICY "venue_self" ON venue_profiles
    FOR ALL USING (auth.uid() = id);
-- Chiunque autenticato può vedere i venue (per info turni)
CREATE POLICY "venue_read_all" ON venue_profiles
    FOR SELECT USING (auth.role() = 'authenticated');

-- Turni: venue crea i propri, tutti leggono i turni aperti
CREATE POLICY "shifts_venue_write" ON shifts
    FOR ALL USING (auth.uid() = venue_id);
CREATE POLICY "shifts_read_open" ON shifts
    FOR SELECT USING (auth.role() = 'authenticated');

-- Applicazioni: worker crea le proprie, venue vede quelle dei propri turni
CREATE POLICY "apps_worker_insert" ON shift_applications
    FOR INSERT WITH CHECK (auth.uid() = worker_id);
CREATE POLICY "apps_worker_read" ON shift_applications
    FOR SELECT USING (auth.uid() = worker_id);
CREATE POLICY "apps_venue_manage" ON shift_applications
    FOR ALL USING (
        auth.uid() IN (SELECT venue_id FROM shifts WHERE id = shift_id)
    );

-- Rating: solo chi è coinvolto può inserire
CREATE POLICY "ratings_insert" ON ratings
    FOR INSERT WITH CHECK (auth.uid() = rater_id);
CREATE POLICY "ratings_read_published" ON ratings
    FOR SELECT USING (is_published = TRUE OR auth.uid() = rater_id);

-- Favorites: solo la venue gestisce le proprie
CREATE POLICY "favorites_venue" ON venue_favorites
    FOR ALL USING (auth.uid() = venue_id);
