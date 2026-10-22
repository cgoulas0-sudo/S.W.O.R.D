"""Small real-Postgres helpers shared across the RT01-B proof modules."""


def scalar(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return row[0] if row else None


def rows(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def exec_(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())


def begin_save(db, ttl_minutes=30):
    """Call the gateway BEGIN and return its returned locator context as a dict."""
    with db.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(%s)", (ttl_minutes,))
        published, staging, lock_token, lock_expires_at = cur.fetchone()
    return {
        "published": published,
        "staging": staging,
        "token": lock_token,
        "expires": lock_expires_at,
    }


def break_glass(db, sql, params=None):
    """Run one owner/superuser DML statement as an intentional break-glass admin.

    RT01-B's guard trigger rejects ungated DML, so an administrator must assert
    the transaction-local guard and perform the write inside the SAME transaction.
    Autocommit would end the transaction between the two statements and drop the
    (transaction-local) guard, so this briefly switches ``db`` into a manual
    transaction, asserts the guard, runs the write, commits, and restores
    autocommit. This models the break-glass path (e.g. simulating elapsed time),
    never a normal gameplay write.
    """
    prev = db.autocommit
    db.autocommit = False
    try:
        with db.cursor() as cur:
            cur.execute("select set_config('rhc.gated_write', 'active', true)")
            cur.execute(sql, params or ())
        db.commit()
    finally:
        db.autocommit = prev


def locator(db):
    """Return the singleton runtime locator as a dict for assertions."""
    with db.cursor() as cur:
        cur.execute(
            """
            select published_generation, published_git_ref, published_day,
                   save_in_progress, staging_generation, lock_token,
                   save_started_at, lock_expires_at
            from public.campaign_runtime where id = 1
            """
        )
        (
            pub_gen,
            git_ref,
            day,
            in_progress,
            staging,
            lock_token,
            started_at,
            expires_at,
        ) = cur.fetchone()
    return {
        "published_generation": pub_gen,
        "published_git_ref": git_ref,
        "published_day": day,
        "save_in_progress": in_progress,
        "staging_generation": staging,
        "lock_token": lock_token,
        "save_started_at": started_at,
        "lock_expires_at": expires_at,
    }
