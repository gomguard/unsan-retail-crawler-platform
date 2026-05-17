import json

from .step00_config import connect


def fetch_dicts(cur, sql):
    cur.execute(sql)
    names = [desc[0] for desc in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def main():
    conn = connect()
    with conn:
        with conn.cursor() as cur:
            active_transactions = fetch_dicts(
                cur,
                """
                SELECT
                  pid,
                  usename,
                  application_name,
                  state,
                  wait_event_type,
                  wait_event,
                  date_trunc('second', now() - xact_start)::text AS xact_age,
                  date_trunc('second', now() - query_start)::text AS query_age,
                  left(query, 240) AS query
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND xact_start IS NOT NULL
                ORDER BY xact_start NULLS LAST
                LIMIT 20
                """,
            )
            ungranted_locks = fetch_dicts(
                cur,
                """
                SELECT
                  a.pid,
                  a.usename,
                  a.application_name,
                  a.state,
                  a.wait_event_type,
                  a.wait_event,
                  l.locktype,
                  l.mode,
                  l.relation::regclass::text AS relation,
                  date_trunc('second', now() - a.query_start)::text AS query_age,
                  left(a.query, 240) AS query
                FROM pg_locks l
                JOIN pg_stat_activity a ON a.pid = l.pid
                WHERE NOT l.granted
                ORDER BY a.query_start NULLS LAST
                LIMIT 20
                """,
            )
    conn.close()
    print(
        json.dumps(
            {
                "active_transactions": active_transactions,
                "ungranted_locks": ungranted_locks,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
