-- SPDX-FileCopyrightText: 2024 Marten Ringwelski
-- SPDX-FileContributor: Marten Ringwelski <git@maringuu.de>
--
-- SPDX-License-Identifier: AGPL-3.0-only

CREATE OR REPLACE FUNCTION
firmup_cte(query_function_id integer, target_binary_id integer)
RETURNS SETOF integer
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    query_binary_id integer;
    ret integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM "function" WHERE id = query_function_id) THEN
        RAISE EXCEPTION 'Query function with id % does not exist', query_function_id;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM "binary" WHERE id = target_binary_id) THEN
        RAISE EXCEPTION 'Target binary with id % does not exist', target_binary_id;
    END IF;

    SELECT binary_id INTO query_binary_id FROM "function" WHERE id = query_function_id;

    IF query_binary_id = target_binary_id THEN
        RAISE EXCEPTION 'Target (%) and query (%) binaries must be different', target_binary_id, query_binary_id;
    END IF;


    RETURN QUERY WITH RECURSIVE matching(
        -- All matched function ids from the query binary
        qf_ids,
        -- The left side of the matching
        qf_id,
        -- All matched function ids from the target binary
        tf_ids,
        -- The right side of the matching
        tf_id,
        -- The similarity of qf_vec and tf_vec
        sim,
        -- The step in the matching.
        -- Odd steps are matching steps and even steps are counter steps
        n,
    	score
    	) AS (
    	SELECT
    	    '{}'::integer[],
    		e.qf_id,
    	    ARRAY[e.tf_id],
    		e.tf_id,
    		e.sim,
    	    1 AS n,
    		1::bigint AS score
    		FROM edges e
    		WHERE qf_id = query_function_id AND sim = (SELECT MAX(sim) FROM edges WHERE qf_id = query_function_id)
    	UNION ALL (
    		SELECT
    			m.qf_ids || ARRAY[e.qf_id],
    	        e.qf_id,
    			m.tf_ids || ARRAY[e.tf_id],
    			e.tf_id,
    			e.sim,
    			m.n + 1,
    			ROW_NUMBER () OVER (ORDER BY e.sim DESC NULLS LAST)
    		FROM matching AS m, edges AS e
    		WHERE
            (
    		-- We are only interested in the top match from last iteration
    		m.score = 1
            AND
            e.sim IS NOT NULL
            AND
            m.sim IS NOT NULL
            ) AND
    		((
    	    -- Find a new match for the query function
    		(m.n % 2) = 0
    		AND
    		-- Match to the query function
    		e.qf_id = query_function_id
    		AND
    		-- Ensure functions are only matched once
    		NOT (e.tf_id = ANY(m.tf_ids))
    		--AND
    		--m.sim < (lshvector_compare(tf.vector, qf.vector)).sim
    		)
    		OR
    		(
    		 -- Counter the matching
    		(m.n % 2) = 1
    		AND
    		-- Match the target function that is currently matched
    		e.tf_id = m.tf_id
    		AND
    		-- Ensure functions are only matched once
    		NOT (e.qf_id = ANY(m.qf_ids))
    		AND
    		-- Ensure that the new matching is actually a counter
    		m.sim < e.sim
    		))
    	)
    ), edges AS (
    	SELECT qf.id as qf_id, tf.id as tf_id, (lshvector_compare(qf.vector, tf.vector)).sim AS sim
    	FROM "function" AS qf, "function" AS tf
    	WHERE qf.binary_id = query_binary_id AND tf.binary_id = target_binary_id
    )
    SELECT tf_id
    FROM matching
    WHERE score = 1 AND n = (SELECT MAX(n) FROM matching);

    END;
$$;


