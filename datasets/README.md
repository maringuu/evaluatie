> Make sure to read data-integrity.ipynb before using this!

# Evaluatie -- Datasets
This directory contains datasets sampled from the database.
Note that we create tables rather than materialized views as we do not want to update
the data. If we want to update, we simply sample again.

```sql
-- For convenience, 'd' is short for 'datasets'.
CREATE SCHEMA d;
```

## Misc
```sql
-- Are there actuall
SELECT ftr.neighborhood_size, ftr.size, count(*)
FROM e.factors ftr
GROUP BY ftr.neighborhood_size, ftr.size
```

## List of Build Parameters
- architecture
- bitness
- noinline
- optimization

## f:o0Xo2
```sql
-- Takes roughly 3 minutes.
-- The part where we select negative pairs is the slowest.
CREATE TABLE d."f:o0Xo2" AS (
	-- Positive pairs
	WITH pairs AS (
		SELECT
			qfd.binary_id AS query_binary_id,
			ptfd.binary_id AS target_binary_id,
			qfd.id AS query_function_id,
			ptfd.id AS ptarget_function_id
		FROM e."function-data" qfd
			JOIN e."function-data" ptfd ON (
				-- Function equivalence
				ptfd.name = qfd.name AND
				ptfd.file = qfd.file AND
				ptfd.lineno = qfd.lineno AND
				ptfd.binary_name = qfd.binary_name AND
				ptfd.package_name = qfd.package_name AND
				ptfd.package_version = qfd.package_version AND
				-- Build parameters
				ptfd.architecture = qfd.architecture AND
				ptfd.bitness = qfd.bitness AND
				ptfd.noinline = qfd.noinline AND
				ptfd.optimisation = 'O2'
			)
		WHERE qfd.optimisation = 'O0'
	), tbl AS (
	SELECT pairs.*,
		ROW_NUMBER() OVER (
			PARTITION BY (
				ftr.size,
				ftr.neighborhood_size
			) ORDER BY ftr.random_id
		) AS sample_number
	FROM pairs
		JOIN e.factors ftr ON (
			pairs.query_function_id = ftr.function_id
		)
	),
	"pairs:positive" AS (
		-- XXX: Missing: label, neighborhood_size, size, function_data?
		SELECT *
		FROM tbl
		WHERE sample_number <= 10000
	)
	SELECT DISTINCT ON (p.query_function_id) p.*, tf.id AS ntarget_function_id
	FROM "pairs:positive" p
		JOIN e.function tf ON (
			tf.binary_id = p.target_binary_id
		)
	ORDER BY p.query_function_id, RANDOM()

);
CREATE INDEX ON d."f:o0Xo2" (query_binary_id);
CREATE INDEX ON d."f:o0Xo2" (target_binary_id);
CREATE INDEX ON d."f:o0Xo2" (query_function_id);
CREATE INDEX ON d."f:o0Xo2" (ptarget_function_id);
CREATE INDEX ON d."f:o0Xo2" (ntarget_function_id);

-- Select a negative pair
-- The negative pair is from the same binary as the positive one.
-- In other words it has the same build parameters as the positive target
-- and is from the same software. The latter is not the case in all papers
-- but makes sense for us, as this is exactly neighbsim's usecase.
SELECT DISTINCT ON (p.query_function_id) p.*, tf.id
FROM d."f:o0Xo2" p
	JOIN e.binary tb ON (
		p.query_binary_id = tb.id
	)
	JOIN e.function tf ON (
		tf.binary_id = tb.id
	)
ORDER BY p.query_function_id, RANDOM()
```

## f:o0Xo3

## f:osXo0

## f:osXo2

## f:osXo3

## f:noinlineXinline
- Spannend, weil das unseren approach stark beeinflusst

## f:x86Xarm
- Spannend weil cisc vs risc

## f:x86Xmips
- Spannend weil cisc vs risc

## f:armXmips
- Spannend weil risc  vs risc

## f:malware-analysis
- Es variieren: optimisation, noinline
- Es bleiben: architecture, bitness

## f:firmware-analysis
- Es variieren: architecture, bitness
- Es bleiben: optimisation, noniline

## f:random
- Es varrieren: architecture, bitness, noinline, optimisation
- Es bleiben: -
- Spannend, weil es halt komplett random ist. Andere paper machen das IMMER so.
  Irgendwie krass, dass keiner das systematisch macht.

## optimization
```sql
(
	SELECT *
	FROM e.factors ftr
		JOIN e."function-data" fd ON (
			ftr.function_id = fd.id
		)
	WHERE ftr.size = 'high' AND fd.optimisation = 'O0'
	ORDER BY RANDOM()
	LIMIT 50000
) UNION ALL (
	SELECT *
	FROM e.factors ftr
		JOIN e."function-data" fd ON (
			ftr.function_id = fd.id
		)
	WHERE ftr.size = 'medium' AND fd.optimisation = 'O0'
	ORDER BY RANDOM()
	LIMIT 50000
) UNION ALL (
	SELECT *
	FROM e.factors ftr
		JOIN e."function-data" fd ON (
			ftr.function_id = fd.id
		)
	WHERE ftr.size = 'low' AND fd.optimisation = 'O0'
	ORDER BY RANDOM()
	LIMIT 50000
)
```

```sql
```

```sql
```

```sql
```

```sql
```

```sql
```

## XO -- Call-Graph [call-graph:xo.csv]
This table contains pairs of binaries that have a different optimisation level,
but identical build parameters otherwise.

Table definition:
```sql
CREATE TABLE IF NOT EXISTS d."call-graph:xo" (
	qb_id integer,
	tb_id integer
);
CREATE INDEX ON d."call-graph:xo" (qb_id);
CREATE INDEX ON d."call-graph:xo" (tb_id);
```

Table population:
```sql
TRUNCATE d."call-graph:xo";

WITH binary_w_bparams AS (
    SELECT qb.*,
        qbp.compiler_backend,
        qbp.compiler_version,
        qbp.optimisation,
        qbp.architecture,
        qbp.bitness,
        qbp.lto,
        qbp.noinline,
        qbp.pie
    FROM v."binary:complete" AS qb JOIN build_parameters qbp ON (
        qb.build_parameters_id = qbp.id
    )
),
binary_pair AS (
	-- Pairs of binaries that differ according to the requirements
	SELECT qb.id AS qb_id, tb.id AS tb_id
	FROM binary_w_bparams AS qb JOIN binary_w_bparams AS tb ON (
		-- Only pairs from the same software
		qb.name = tb.name AND
		qb.package_version = tb.package_version AND
		qb.package_name = tb.package_name AND
		-- Build Parameter requirements
		qb.compiler_backend = tb.compiler_backend AND
		qb.compiler_version = tb.compiler_version AND
		qb.optimisation != tb.optimisation AND
		qb.architecture = tb.architecture AND
		qb.bitness = tb.bitness AND
		qb.lto = tb.lto AND
		qb.noinline = tb.noinline AND
		qb.pie = tb.pie AND
		-- Avoid having the same pair twice
		qb.id < tb.id
	)
	ORDER BY RANDOM()
	LIMIT 10000
)
INSERT INTO d."call-graph:xo"
SELECT *
FROM binary_pair
```

Export:
```
COPY d."call-graph:xo" TO '/tmp/call-graph:xo.csv'
WITH (
	FORMAT 'csv',
	HEADER TRUE
);

docker cp studeerwerk-postgres:/tmp/call-graph:xo.csv .
```

## XO -- Call-Graph [call-graph:xaxb.csv]
This table contains pairs of binaries that have a different architecture and bitness,
but identical build parameters otherwise.

Table definition:
```sql
CREATE TABLE IF NOT EXISTS d."call-graph:xaxb" (
	qb_id integer,
	tb_id integer
);
CREATE INDEX ON d."call-graph:xaxb" (qb_id);
CREATE INDEX ON d."call-graph:xaxb" (tb_id);
```

Table population:
```sql
TRUNCATE d."call-graph:xaxb";

WITH binary_w_bparams AS (
    SELECT qb.*,
        qbp.compiler_backend,
        qbp.compiler_version,
        qbp.optimisation,
        qbp.architecture,
        qbp.bitness,
        qbp.lto,
        qbp.noinline,
        qbp.pie
    FROM v."binary:complete" AS qb JOIN build_parameters qbp ON (
        qb.build_parameters_id = qbp.id
    )
),
binary_pair AS (
	-- Pairs of binaries that differ according to the requirements
	SELECT qb.id AS qb_id, tb.id AS tb_id
	FROM binary_w_bparams AS qb JOIN binary_w_bparams AS tb ON (
		-- Only pairs from the same software
		qb.name = tb.name AND
		qb.package_version = tb.package_version AND
		qb.package_name = tb.package_name AND
		-- Build Parameter requirements
		qb.compiler_backend = tb.compiler_backend AND
		qb.compiler_version = tb.compiler_version AND
		qb.optimisation = tb.optimisation AND
		qb.architecture != tb.architecture AND
		qb.bitness != tb.bitness AND
		qb.lto = tb.lto AND
		qb.noinline = tb.noinline AND
		qb.pie = tb.pie AND
		-- Avoid having the same pair twice
		qb.id < tb.id
	)
	ORDER BY RANDOM()
	LIMIT 10000
)
INSERT INTO d."call-graph:xaxb"
SELECT *
FROM binary_pair
```

Export:
```
COPY d."call-graph:xaxb" TO '/tmp/call-graph:xaxb.csv'
WITH (
	FORMAT 'csv',
	HEADER TRUE
);

docker cp studeerwerk-postgres:/tmp/call-graph:xaxb.csv .
```

## XO -- Call-Graph [call-graph:xo:o0xo3.csv]
This table contains pairs of binaries where one binary is compiled with o0 and the other with o3,
but identical build parameters otherwise.

Table definition:
```sql
CREATE TABLE IF NOT EXISTS d."call-graph:xo:o0xo3" (
	qb_id integer,
	tb_id integer
);
CREATE INDEX ON d."call-graph:xo:o0xo3" (qb_id);
CREATE INDEX ON d."call-graph:xo:o0xo3" (tb_id);
```

Table population:
```sql
TRUNCATE d."call-graph:xo:o0xo3";

WITH binary_w_bparams AS (
    SELECT qb.*,
        qbp.compiler_backend,
        qbp.compiler_version,
        qbp.optimisation,
        qbp.architecture,
        qbp.bitness,
        qbp.lto,
        qbp.noinline,
        qbp.pie
    FROM v."binary:complete" AS qb JOIN build_parameters qbp ON (
        qb.build_parameters_id = qbp.id
    )
),
binary_pair AS (
	-- Pairs of binaries that differ according to the requirements
	SELECT qb.id AS qb_id, tb.id AS tb_id
	FROM binary_w_bparams AS qb JOIN binary_w_bparams AS tb ON (
		-- Only pairs from the same software
		qb.name = tb.name AND
		qb.package_version = tb.package_version AND
		qb.package_name = tb.package_name AND
		-- Build Parameter requirements
		qb.compiler_backend = tb.compiler_backend AND
		qb.compiler_version = tb.compiler_version AND
		qb.optimisation = 'O0' AND
		tb.optimisation = 'O3' AND
		qb.architecture = tb.architecture AND
		qb.bitness = tb.bitness AND
		qb.lto = tb.lto AND
		qb.noinline = tb.noinline AND
		qb.pie = tb.pie AND
		-- Avoid having the same pair twice
		qb.id < tb.id
	)
	ORDER BY RANDOM()
	LIMIT 10000
)
INSERT INTO d."call-graph:xo:o0xo3"
SELECT *
FROM binary_pair
```

Export:
```
COPY d."call-graph:xo:o0xo3" TO '/tmp/call-graph:xo:o0xo3.csv'
WITH (
	FORMAT 'csv',
	HEADER TRUE
);

docker cp studeerwerk-postgres:/tmp/call-graph:xo:o0xo3.csv .
```

## XO -- Call-Graph [call-graph:xo:o2xo3.csv]
This table contains pairs of binaries where one binary is compiled with o2 and the other with o3,
but identical build parameters otherwise.

Table definition:
```sql
CREATE TABLE IF NOT EXISTS d."call-graph:xo:o2xo3" (
	qb_id integer,
	tb_id integer
);
CREATE INDEX ON d."call-graph:xo:o2xo3" (qb_id);
CREATE INDEX ON d."call-graph:xo:o2xo3" (tb_id);
```

Table population:
```sql
TRUNCATE d."call-graph:xo:o2xo3";

WITH binary_w_bparams AS (
    SELECT qb.*,
        qbp.compiler_backend,
        qbp.compiler_version,
        qbp.optimisation,
        qbp.architecture,
        qbp.bitness,
        qbp.lto,
        qbp.noinline,
        qbp.pie
    FROM v."binary:complete" AS qb JOIN build_parameters qbp ON (
        qb.build_parameters_id = qbp.id
    )
),
binary_pair AS (
	-- Pairs of binaries that differ according to the requirements
	SELECT qb.id AS qb_id, tb.id AS tb_id
	FROM binary_w_bparams AS qb JOIN binary_w_bparams AS tb ON (
		-- Only pairs from the same software
		qb.name = tb.name AND
		qb.package_version = tb.package_version AND
		qb.package_name = tb.package_name AND
		-- Build Parameter requirements
		qb.compiler_backend = tb.compiler_backend AND
		qb.compiler_version = tb.compiler_version AND
		qb.optimisation = 'O2' AND
		tb.optimisation = 'O3' AND
		qb.architecture = tb.architecture AND
		qb.bitness = tb.bitness AND
		qb.lto = tb.lto AND
		qb.noinline = tb.noinline AND
		qb.pie = tb.pie AND
		-- Avoid having the same pair twice
		qb.id < tb.id
	)
	ORDER BY RANDOM()
	LIMIT 10000
)
INSERT INTO d."call-graph:xo:o2xo3"
SELECT *
FROM binary_pair
```

Export:
```
COPY d."call-graph:xo:o2xo3" TO '/tmp/call-graph:xo:o2xo3.csv'
WITH (
	FORMAT 'csv',
	HEADER TRUE
);

docker cp studeerwerk-postgres:/tmp/call-graph:xo:o2xo3.csv .
```


# Creating buckets
```sql
-- Get the percentiles of the set of evaluation functions that we have
SELECT
	PERCENTILE_CONT(0.33) WITHIN GROUP (ORDER BY size) AS size_p33, -- 3
	PERCENTILE_CONT(0.66) WITHIN GROUP (ORDER BY size) AS size_p66, -- 10
	PERCENTILE_CONT(0.33) WITHIN GROUP (ORDER BY complexity) AS complexity_p33, -- 1
	PERCENTILE_CONT(0.66) WITHIN GROUP (ORDER BY complexity) AS complexity_p66, -- 5
	PERCENTILE_CONT(0.33) WITHIN GROUP (ORDER BY neighborhood_size) AS neighborhood_size_p33, -- 1
	PERCENTILE_CONT(0.66) WITHIN GROUP (ORDER BY neighborhood_size) AS neighborhood_size_p66 -- 3
FROM e."factors:raw" fr

CREATE MATERIALIZED VIEW e."factors" AS (
    SELECT
        fr.function_id,
        fr.random_id,
        fr.optimisation,
        fr.architecture,
        fr.bitness,
        fr.noinline,
        fr.package,
        CASE
            WHEN fr.size <= 3 THEN 'low'
            WHEN fr.size <= 10 THEN 'medium'
            ELSE 'high'
        END AS size,
        CASE
            WHEN fr.complexity <= 1 THEN 'low'
            WHEN fr.complexity <= 5 THEN 'medium'
            ELSE 'high'
        END AS complexity,
        CASE
            WHEN fr.neighborhood_size <= 1 THEN 'low'
            WHEN fr.neighborhood_size <= 3 THEN 'medium'
            ELSE 'high'
        END AS neighborhood_size
    FROM e."factors:raw" fr
);
CREATE INDEX ON e.factors (function_id);
CREATE INDEX ON e.factors (optimisation);
CREATE INDEX ON e.factors (architecture);
CREATE INDEX ON e.factors (bitness);
CREATE INDEX ON e.factors (noinline);
CREATE INDEX ON e.factors (package);
CREATE INDEX ON e.factors (size);
CREATE INDEX ON e.factors (complexity);
CREATE INDEX ON e.factors (neighborhood_size);
-- To speed up the partitioning below
CREATE INDEX ON e.factors (function_id, optimisation, architecture, bitness, noinline, package, size, complexity, neighborhood_size, random_id);


-- How many factor combinations are there?
SELECT DISTINCT fctr.optimisation,
    fctr.architecture,
    fctr.bitness,
    fctr.noinline,
    fctr.package,
    fctr.size,
    fctr.complexity,
    fctr.neighborhood_size
FROM e.factors fctr


-- Functions with data to find equivalent functions
CREATE MATERIALIZED VIEW e."function-data" AS (
	SELECT f.id, f.name, f.file, f.lineno, f.vector, f.binary_id, b.name AS binary_name, b.package_version, b.package_name, bp.compiler_backend, bp.optimisation, bp.architecture, bp.bitness, bp.lto, bp.noinline, bp.pie, bp.id AS build_parameters_id
	FROM e.function f
		JOIN e.binary b ON (
			f.binary_id = b.id
		)
		JOIN build_parameters bp ON (
			b.build_parameters_id = bp.id
		)
);
-- All these indices take about 5 minutes to build.
CREATE INDEX ON e."function-data" (id);
CREATE INDEX ON e."function-data" (build_parameters_id);
CREATE INDEX ON e."function-data" (name);
CREATE INDEX ON e."function-data" (file);
CREATE INDEX ON e."function-data" (lineno);
CREATE INDEX ON e."function-data" (binary_id);
CREATE INDEX ON e."function-data" (binary_name);
CREATE INDEX ON e."function-data" (package_version);
CREATE INDEX ON e."function-data" (package_name);
CREATE INDEX ON e."function-data" (compiler_backend);
CREATE INDEX ON e."function-data" (optimisation);
CREATE INDEX ON e."function-data" (architecture);
CREATE INDEX ON e."function-data" (bitness);
CREATE INDEX ON e."function-data" (lto);
CREATE INDEX ON e."function-data" (noinline);
CREATE INDEX ON e."function-data" (pie);
-- For checking equivalence of various factors.
-- Note that the last factor is the one we check for a specific value.
-- All others should be the same.
CREATE INDEX ON e."function-data" (
    architecture,
    bitness,
    noinline,
    optimisation
);
CREATE INDEX ON e."function-data" (
    bitness,
    noinline,
    optimisation,
    architecture
);
CREATE INDEX ON e."function-data" (
    architecture,
    noinline,
    optimisation,
    bitness
);
CREATE INDEX ON e."function-data" (
    architecture,
    bitness,
    optimisation,
    noinline
);
-- For implementation equality.
CREATE INDEX ON e."function-data" (
    package_name,
    package_version,
    binary_name,
    file,
    lineno,
    name
);
-- For sampling konwn negatives from the same binary.
CREATE INDEX ON e."function-data" (
    package_name,
    package_version,
    binary_name
);
```
