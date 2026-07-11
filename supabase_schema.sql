-- ============================================================
-- AURA — Supabase SQL Schema (Idempotent)
--
-- Safe to run on a brand-new empty Supabase project.
-- All statements use IF NOT EXISTS / ON CONFLICT for safety.
--
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================


-- ========================
-- 1. PRODUCTS TABLE
-- ========================
CREATE TABLE IF NOT EXISTS products (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    price       NUMERIC(10,2) DEFAULT 0,
    brand       TEXT DEFAULT 'Philips',
    category    TEXT DEFAULT '',
    aliases     TEXT[] DEFAULT '{}',
    warranty_years INTEGER DEFAULT 1,
    manual_url  TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Seed products removed. Table will be populated via admin panel.


-- ========================
-- 2. ORDERS TABLE
-- ========================
CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,
    customer_name   TEXT NOT NULL,
    customer_phone  TEXT DEFAULT '',
    product_id      TEXT REFERENCES products(id),
    product_name    TEXT DEFAULT '',
    status          TEXT DEFAULT 'Pending'
                    CHECK (status IN ('Pending','Processing','In-Transit','Delivered','Cancelled')),
    purchase_date   DATE,
    warranty_years  INTEGER DEFAULT 1,
    serial_number   TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Upgrade existing orders table
ALTER TABLE orders DROP COLUMN IF EXISTS customer_email;

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

-- Seed orders removed. Table will be populated via /admin/import-orders endpoint.


-- ========================
-- 3. REFUNDS TABLE
-- ========================
CREATE TABLE IF NOT EXISTS refunds (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    refund_id   TEXT UNIQUE NOT NULL,
    order_id    TEXT REFERENCES orders(id),
    product_name TEXT DEFAULT '',
    user_email  TEXT DEFAULT '',
    user_name   TEXT DEFAULT '',
    reason      TEXT DEFAULT '',
    status      TEXT DEFAULT 'processing'
                CHECK (status IN ('processing','approved','rejected','completed')),
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_refunds_status ON refunds(status);


-- ========================
-- 4. REPLACEMENTS TABLE
-- ========================
CREATE TABLE IF NOT EXISTS replacements (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    replacement_id  TEXT UNIQUE NOT NULL,
    order_id        TEXT REFERENCES orders(id),
    product_name    TEXT DEFAULT '',
    user_email      TEXT DEFAULT '',
    user_name       TEXT DEFAULT '',
    reason          TEXT DEFAULT '',
    status          TEXT DEFAULT 'processing'
                    CHECK (status IN ('processing','approved','dispatched','completed')),
    created_at      TIMESTAMPTZ DEFAULT now()
);


-- ========================
-- 5. SERVICE BOOKINGS TABLE
-- ========================
CREATE TABLE IF NOT EXISTS service_bookings (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id      TEXT UNIQUE NOT NULL,
    order_id        TEXT REFERENCES orders(id),
    product_name    TEXT DEFAULT '',
    user_email      TEXT DEFAULT '',
    user_name       TEXT DEFAULT '',
    user_address    TEXT DEFAULT '',
    contact_number  TEXT DEFAULT '',
    service_center  TEXT DEFAULT 'Nearest Center',
    scheduled_date  TEXT DEFAULT 'TBD',
    time_slot       TEXT DEFAULT 'TBD',
    created_at      TIMESTAMPTZ DEFAULT now()
);


-- ========================
-- 6. KNOWLEDGE BASE TABLE
-- ========================
CREATE TABLE IF NOT EXISTS knowledge_base (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_name       TEXT NOT NULL,
    bucket_path     TEXT DEFAULT '',
    document_type   TEXT DEFAULT 'manual'
                    CHECK (document_type IN ('manual','policy','faq','other')),
    status          TEXT DEFAULT 'pending'
                    CHECK (status IN ('pending','indexing','ready','error')),
    chunks_count    INTEGER DEFAULT 0,
    last_indexed    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);


-- ========================
-- 6b. POLICIES TABLE
-- ========================
CREATE TABLE IF NOT EXISTS policies (
    id              TEXT PRIMARY KEY,
    policy_type     TEXT NOT NULL
                    CHECK (policy_type IN ('refund','replacement','warranty')),
    scope           TEXT NOT NULL DEFAULT 'global'
                    CHECK (scope IN ('global','category')),
    category        TEXT,
    rules           JSONB DEFAULT '{}',
    description     TEXT DEFAULT '',
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Unique constraint: only one policy per type+scope+category combo
CREATE UNIQUE INDEX IF NOT EXISTS idx_policies_type_scope_category
    ON policies(policy_type, scope, COALESCE(category, ''));


-- ========================
-- 7. CHAT SESSIONS TABLE
-- ========================
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  TEXT UNIQUE NOT NULL,
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    title       TEXT DEFAULT 'New Chat',
    status      TEXT DEFAULT 'active'
                CHECK (status IN ('active','handed_over','closed')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Upgrade existing tables if they already existed before Phase 6.5
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS title TEXT DEFAULT 'New Chat';
ALTER TABLE chat_sessions DROP COLUMN IF EXISTS customer_name;

-- ========================
-- 8. CHAT MESSAGES TABLE
-- ========================
CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  TEXT REFERENCES chat_sessions(session_id),
    role        TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
    content     TEXT NOT NULL,
    sources     JSONB DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);


-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================

ALTER TABLE products        ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders          ENABLE ROW LEVEL SECURITY;
ALTER TABLE refunds         ENABLE ROW LEVEL SECURITY;
ALTER TABLE replacements    ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_base  ENABLE ROW LEVEL SECURITY;
ALTER TABLE policies        ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages   ENABLE ROW LEVEL SECURITY;

-- Public read access for products (for the chat widget)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE policyname = 'Products are publicly readable' AND tablename = 'products'
  ) THEN
    CREATE POLICY "Products are publicly readable" ON products FOR SELECT USING (true);
  END IF;
END $$;

-- Public read access for policies (for the chat widget to resolve policies)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE policyname = 'Policies are publicly readable' AND tablename = 'policies'
  ) THEN
    CREATE POLICY "Policies are publicly readable" ON policies FOR SELECT USING (true);
  END IF;
END $$;

-- Authenticated users can read orders (for API lookups)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Authenticated users can read orders' AND tablename = 'orders') THEN
    CREATE POLICY "Authenticated users can read orders" ON orders FOR SELECT USING (auth.role() = 'authenticated');
  END IF;
END $$;

-- Strict RLS for chat_sessions: Users can only see their own sessions
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can manage their own chat sessions' AND tablename = 'chat_sessions') THEN
    CREATE POLICY "Users can manage their own chat sessions" ON chat_sessions FOR ALL USING (auth.uid() = user_id);
  END IF;
END $$;

-- Strict RLS for chat_messages: Users can only see messages in their own sessions
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can manage their own chat messages' AND tablename = 'chat_messages') THEN
    CREATE POLICY "Users can manage their own chat messages" ON chat_messages FOR ALL USING (
      EXISTS (
        SELECT 1 FROM chat_sessions
        WHERE chat_sessions.session_id = chat_messages.session_id
        AND chat_sessions.user_id = auth.uid()
      )
    );
  END IF;
END $$;

-- Authenticated admin users can manage all data
-- The service_role key bypasses RLS by default in Supabase.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Admin full access to orders' AND tablename = 'orders') THEN
    CREATE POLICY "Admin full access to orders" ON orders FOR ALL USING (auth.role() = 'authenticated');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Admin full access to refunds' AND tablename = 'refunds') THEN
    CREATE POLICY "Admin full access to refunds" ON refunds FOR ALL USING (auth.role() = 'authenticated');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Admin full access to replacements' AND tablename = 'replacements') THEN
    CREATE POLICY "Admin full access to replacements" ON replacements FOR ALL USING (auth.role() = 'authenticated');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Admin full access to service_bookings' AND tablename = 'service_bookings') THEN
    CREATE POLICY "Admin full access to service_bookings" ON service_bookings FOR ALL USING (auth.role() = 'authenticated');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Admin full access to knowledge_base' AND tablename = 'knowledge_base') THEN
    CREATE POLICY "Admin full access to knowledge_base" ON knowledge_base FOR ALL USING (auth.role() = 'authenticated');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Admin full access to chat_sessions' AND tablename = 'chat_sessions') THEN
    CREATE POLICY "Admin full access to chat_sessions" ON chat_sessions FOR ALL USING (auth.role() = 'authenticated');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Admin full access to chat_messages' AND tablename = 'chat_messages') THEN
    CREATE POLICY "Admin full access to chat_messages" ON chat_messages FOR ALL USING (auth.role() = 'authenticated');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Admin full access to products' AND tablename = 'products') THEN
    CREATE POLICY "Admin full access to products" ON products FOR ALL USING (auth.role() = 'authenticated');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Admin full access to policies' AND tablename = 'policies') THEN
    CREATE POLICY "Admin full access to policies" ON policies FOR ALL USING (auth.role() = 'authenticated');
  END IF;
END $$;


-- ============================================================
-- SUPABASE STORAGE — MANUALS BUCKET
-- ============================================================
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES ('manuals', 'manuals', true, 10485760)
ON CONFLICT (id) DO NOTHING;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public read access for manuals' AND tablename = 'objects') THEN
    CREATE POLICY "Public read access for manuals"
      ON storage.objects FOR SELECT
      USING (bucket_id = 'manuals');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Authenticated users can upload manuals' AND tablename = 'objects') THEN
    CREATE POLICY "Authenticated users can upload manuals"
      ON storage.objects FOR INSERT
      WITH CHECK (bucket_id = 'manuals' AND auth.role() = 'authenticated');
  END IF;
END $$;
