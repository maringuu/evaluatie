> Make sure to read data-integrity.ipynb before using this!

# Evaluatie -- Datasets
This directory contains datasets sampled from the database.
Note that we create tables rather than materialized views as we do not want to update
the data. If we want to update, we simply sample again.

```sql
-- For convenience, 'd' is short for 'datasets'.
CREATE SCHEMA d;
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
