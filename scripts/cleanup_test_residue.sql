-- One-shot cleanup: delete test residue from the production database (ROADMAP Wave 0 #11a).
--
-- WHY THIS EXISTS
-- `app/config.py` falls back to `server/.env` when DATABASE_URL is unset, and on the deploy
-- host that file points at the live `magpie` DB. So a bare local `pytest` ran the whole suite
-- against production, accumulating ~456 test users, ~402 accounts and 464 transactions there.
-- The source is fixed (tests/conftest.py now pins the database name to `*_test` and refuses
-- anything else); this script removes what was already written.
--
-- The real financial data was never corrupted: every service is user-scoped, so test rows only
-- ever hung off test users. This deletes those users and lets ON DELETE CASCADE take their
-- accounts, transactions, ingest_events, rules, budgets, categories, latches, bill_statements
-- and statement_checkpoints with them.
--
-- PRESERVED, deliberately:
--   * the real household user and its 5 accounts / 4,745 transactions;
--   * `magpie-smoke` (dragonfly-id's synthetic-smoke user) — it is deploy-gate infrastructure,
--     not residue, and it owns zero transactions;
--   * `import_batches` — that table has no user_id and no FK to one (a real design gap: it
--     cannot be attributed, so it cannot be safely pruned here). ~88 of its 119 rows are test
--     provenance. Scoping it to a user is the proper fix, not a DELETE.
--
-- RUN IT (take the dump first — this is financial history):
--   docker exec magpie-db-1 pg_dump -U magpie -d magpie > magpie-pre-cleanup-$(date +%F).sql
--   docker exec -i magpie-db-1 psql -U magpie -d magpie -v ON_ERROR_STOP=1 < scripts/cleanup_test_residue.sql
--
-- The transaction aborts itself if the real user's transaction count moves by even one row.

\set ON_ERROR_STOP on

BEGIN;

-- The definition of "test user", used identically for the snapshot and the delete.
CREATE TEMP VIEW _test_users AS
SELECT id FROM users
WHERE email LIKE '%@magpie.test'
   OR email LIKE '%@example.com'
   OR email LIKE '%.invalid';

-- Snapshot every row that must survive, before touching anything.
CREATE TEMP TABLE _before AS
SELECT count(*) AS real_txns
FROM transactions t
JOIN accounts a ON t.account_id = a.id
WHERE a.user_id NOT IN (SELECT id FROM _test_users);

DELETE FROM users WHERE id IN (SELECT id FROM _test_users);

-- Tripwire. If the cascade reached one real transaction, abort the whole thing.
DO $$
DECLARE
    before_n bigint;
    after_n  bigint;
BEGIN
    SELECT real_txns INTO before_n FROM _before;
    SELECT count(*) INTO after_n
    FROM transactions t
    JOIN accounts a ON t.account_id = a.id
    JOIN users u ON a.user_id = u.id
    WHERE u.email NOT LIKE '%@magpie.test'
      AND u.email NOT LIKE '%@example.com'
      AND u.email NOT LIKE '%.invalid';

    IF before_n <> after_n THEN
        RAISE EXCEPTION 'ABORT: real transactions changed % -> % (nothing was deleted)',
            before_n, after_n;
    END IF;

    RAISE NOTICE 'OK: % real transactions preserved', after_n;
END $$;

COMMIT;

-- Post-cleanup verification.
SELECT 'users' AS table, count(*) FROM users
UNION ALL SELECT 'accounts', count(*) FROM accounts
UNION ALL SELECT 'transactions', count(*) FROM transactions
UNION ALL SELECT 'ingest_events', count(*) FROM ingest_events;
