-- SPDX-FileCopyrightText: 2024 Marten Ringwelski
-- SPDX-FileContributor: Marten Ringwelski <git@maringuu.de>
--
-- SPDX-License-Identifier: AGPL-3.0-only

/*

SELECT "query".name, target.name
FROM "function" AS target,(
    SELECT firmup(fun.id, 107) AS target_id, fun.name
    FROM (SELECT fun.id, fun.name FROM "function" fun WHERE fun.binary_id = 65) AS fun
    LIMIT 20
) AS "query"
WHERE "query".target_id = target.id

*/
CREATE OR REPLACE FUNCTION
firmup(query_function_id integer, target_binary_id integer)
RETURNS integer
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    query_binary_id integer;
    query_function_vector lshvector;
    tf_ids integer[];
    qf_ids integer[];
BEGIN
    IF NOT EXISTS (SELECT 1 FROM "function" WHERE id = query_function_id) THEN
        RAISE EXCEPTION 'Query function with id % does not exist', query_function_id;
    END IF;

    SELECT vector INTO query_function_vector FROM "function" WHERE id = query_function_id;

    IF query_function_vector IS NULL THEN
        RAISE EXCEPTION 'Query function % has no associated vector', query_function_id;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM "binary" WHERE id = target_binary_id) THEN
        RAISE EXCEPTION 'Target binary with id % does not exist', target_binary_id;
    END IF;

    SELECT binary_id INTO query_binary_id FROM "function" WHERE id = query_function_id;

    IF query_binary_id = target_binary_id THEN
        RAISE EXCEPTION 'Target (%) and query (%) binaries must be different', target_binary_id, query_binary_id;
    END IF;


    <<block>>
    DECLARE
        target_binary_function_id integer;
        target_binary_function_vector lshvector;
        query_function_counter_id integer;
        i integer = 1;
    BEGIN
        LOOP
            -- RAISE NOTICE '';
            -- RAISE NOTICE 'query_function_id %', query_function_id;

            SELECT tf.id, tf.vector INTO block.target_binary_function_id, block.target_binary_function_vector
            FROM "function" AS tf
            WHERE NOT (tf.id = ANY(tf_ids))
                AND tf.binary_id = target_binary_id
            ORDER BY (lshvector_compare(query_function_vector, tf.vector)).sim DESC
            LIMIT 1;
            tf_ids[i] = target_binary_function_id;

            -- RAISE NOTICE 'target_binary_function_id %', target_binary_function_id;

            SELECT qf.id INTO block.query_function_counter_id
            FROM "function" AS qf
            WHERE NOT (qf.id = ANY(qf_ids))
                AND qf.binary_id = query_binary_id
            ORDER BY (lshvector_compare(qf.vector, block.target_binary_function_vector)).sim DESC
            LIMIT 1;
            -- RAISE NOTICE 'query_function_counter_id %', query_function_counter_id;
            qf_ids[i] = query_function_counter_id;

            -- There are no functions left that we could match the query function too
            IF target_binary_function_id IS NULL THEN
                RETURN NULL;
            END IF;

            -- We successfully found the match for the query function
            IF query_function_id = query_function_counter_id THEN
                RETURN target_binary_function_id;
            END IF;

            i = i + 1;
        END LOOP;
    END;

END;
$$;
