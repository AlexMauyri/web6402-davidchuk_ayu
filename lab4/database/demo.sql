-- Аккаунты: demo_user (участник), demo_moderator (модератор).
-- Общий публичный пароль: TempleOS-demo-2026!
BEGIN;

SELECT pg_advisory_xact_lock(2026, 4);

DO $$
DECLARE
    demo_hash constant text := '$argon2id$v=19$m=65536,t=3,p=4$ZSrY99rnKYbrTG9UFe/qyA$+q0f1d3R2glnfA+LznnqzAFc2PfqajY4MoAk/t/ZKE8';
BEGIN
    IF EXISTS (
        SELECT 1 FROM users
        WHERE login IN ('demo_user', 'demo_moderator')
          AND (password_hash <> demo_hash
               OR role <> CASE login WHEN 'demo_moderator' THEN 'moderator' ELSE 'user' END)
    ) THEN
        RAISE EXCEPTION 'Тестовый логин уже занят или аккаунт изменён. Наполнение отменено без перезаписи данных.';
    END IF;

    INSERT INTO users (login, password_hash, role)
    VALUES ('demo_user', demo_hash, 'user'),
           ('demo_moderator', demo_hash, 'moderator')
    ON CONFLICT (login) DO NOTHING;
END;
$$;

WITH demo_topics AS (
    SELECT n,
           '[Демо] ' || (ARRAY[
               'Знакомство с TempleOS',
               'Первые шаги в HolyC',
               'Графика и палитра EGA',
               'Документы DolDoc',
               'Файловая система RedSea'
           ])[((n - 1) % 5) + 1] || ' — обсуждение ' || n AS title,
           CASE WHEN n % 5 = 0 THEN 'demo_moderator' ELSE 'demo_user' END AS login
    FROM generate_series(1, 25) AS series(n)
)
INSERT INTO threads (title, text, created_by, created_at)
SELECT topic.title,
       E'Демонстрационная тема для знакомства с форумом TempleOS.\n\n'
       || 'Какие особенности системы вам интересны? Поделитесь опытом изучения HolyC и интерфейса TempleOS.',
       author.id,
       TIMESTAMPTZ '2026-01-01 12:00:00+00' + topic.n * INTERVAL '1 hour'
FROM demo_topics AS topic
JOIN users AS author ON author.login = topic.login
WHERE NOT EXISTS (
    SELECT 1 FROM threads AS existing
    WHERE existing.title = topic.title AND existing.created_by = author.id
);

WITH demo_threads AS (
    SELECT thread.id, thread.title, thread.created_at
    FROM threads AS thread
    JOIN users AS author ON author.id = thread.created_by
    WHERE author.login IN ('demo_user', 'demo_moderator')
      AND thread.title LIKE '[Демо] %'
), demo_comments AS (
    SELECT thread.*, n,
           '[Демо] Комментарий ' || n || E'.\n'
           || CASE WHEN n % 2 = 0
               THEN 'Интересно разобраться, как HolyC объединяет язык программирования и командную оболочку.'
               ELSE 'Предлагаю начать с документации и небольших примеров в самой TempleOS.'
           END AS text
    FROM demo_threads AS thread
    CROSS JOIN LATERAL generate_series(
        1, CASE WHEN thread.title = '[Демо] Знакомство с TempleOS — обсуждение 1' THEN 25 ELSE 2 END
    ) AS series(n)
)
INSERT INTO comments (thread_id, user_id, text, created_at)
SELECT comment.id, author.id, comment.text,
       comment.created_at + comment.n * INTERVAL '1 minute'
FROM demo_comments AS comment
JOIN users AS author ON author.login = CASE WHEN comment.n % 2 = 0 THEN 'demo_moderator' ELSE 'demo_user' END
WHERE NOT EXISTS (
    SELECT 1 FROM comments AS existing
    WHERE existing.thread_id = comment.id
      AND existing.user_id = author.id
      AND existing.text = comment.text
);

COMMIT;
