<!--
SPDX-FileCopyrightText: 2024 Marten Ringwelski
SPDX-FileContributor: Marten Ringwelski <git@maringuu.de>

SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Evaluatie - Code for the Evaluation of my Master's Thesis
This repository contains a python module and accompanying jupyter notebooks.

## Installation
Use `evaluatie-initdb` to initalize the postgres databse.

### Configuring postgresql
As the database gets quite big, we need to tune some postgres configuration to get reasonable good performance.
```
# Postgres docs recommend 25% of memory.
shared_buffers = 16GB
#
work_mem = 2GB
```

### Creating Views
To allow postgres to do fast queries on foreign tables, we use materialized views with custom indices.
All views are created in a separate schema.

```sql
-- 'v' is short for 'view'. It empathises that this is not the
-- data created by the evaluatie python module.
CREATE SCHEMA v;
```

Copy relevant tables:
```sql
-- Create materialized views with coresponding indices for remote tables
-- If this is too slow, using pg_restore --table might be faster

-- Takes ~5 minutes for 58,000,000 rows
CREATE MATERIALIZED VIEW IF NOT EXISTS v.bsim_callgraphtable AS (
    SELECT *
    FROM bsim.callgraphtable
);
CREATE INDEX IF NOT EXISTS ix_bsim_callgraphtable_src ON v.bsim_callgraphtable (src);
CREATE INDEX IF NOT EXISTS ix_bsim_callgraphtable_dest ON v.bsim_callgraphtable (dest);

-- Takes ~5 minutes for 18,000,000 rows
SELECT lsh_reload();
CREATE MATERIALIZED VIEW IF NOT EXISTS v.bsim_vectable AS (
    SELECT *
    FROM bsim.vectable
);
CREATE INDEX IF NOT EXISTS ix_bsim_vectable_id ON v.bsim_vectable (id);
-- XXX indices

-- Takes ~2 minutes for 20,000,000 rows
CREATE MATERIALIZED VIEW IF NOT EXISTS v.bsim_desctable AS (
    SELECT *
    FROM bsim.desctable
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_bsim_desctable_id ON v.bsim_desctable (id);
CREATE INDEX IF NOT EXISTS ix_bsim_desctable_name_func ON v.bsim_desctable (name_func);
CREATE INDEX IF NOT EXISTS ix_bsim_desctable_id_signature ON v.bsim_desctable (id_signature);
CREATE INDEX IF NOT EXISTS ix_bsim_desctable_id_exe ON v.bsim_desctable (id_exe);
CREATE INDEX IF NOT EXISTS ix_bsim_desctable_id_addr ON v.bsim_desctable (addr);
CREATE INDEX IF NOT EXISTS ix_bsim_desctable_id_flags ON v.bsim_desctable (flags);

CREATE MATERIALIZED VIEW IF NOT EXISTS v.bsim_exetable AS (
    SELECT *
    FROM bsim.exetable
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_bsim_exetable_id ON v.bsim_exetable (id);
CREATE INDEX IF NOT EXISTS ix_bsim_exetable_md5 ON v.bsim_exetable (md5);
CREATE INDEX IF NOT EXISTS ix_bsim_exetable_name_exec ON v.bsim_exetable (name_exec);
```

Now, create some views that we will use afterwards:
```sql
-- Mapping ghidra executables to evaluatie binaries
CREATE MATERIALIZED VIEW IF NOT EXISTS v.executable2binary AS (
    SELECT b.id as binary_id, e.id as executable_id
        FROM "binary" AS b
        JOIN bsim.exetable AS e
        ON b.md5 = e.md5
);
CREATE INDEX ix_executable2binary_executable_id ON v.executable2binary (executable_id);
CREATE INDEX ix_executable2binary_binary_id ON v.executable2binary (binary_id);


-- Exactly the same as 'binary' but with corrected image_base.
-- We must create this early, to be able to use it later.
CREATE MATERIALIZED VIEW v.binary AS (
	WITH function_data AS (
		SELECT f.id AS id, f.offset + b.image_base AS address, b.id AS binary_id, f.name
		FROM "function" AS f JOIN "binary" AS b ON f.binary_id = b.id
	),
	-- All named descriptions that do not have a corresponding function
	description_wo_function AS (
		SELECT description.id AS description_id, e2b.executable_id, e2b.binary_id, description.addr, description.name_func AS name
		FROM v.bsim_desctable AS description
			JOIN v.executable2binary e2b ON (
				description.id_exe = e2b.executable_id
			)
			LEFT OUTER JOIN function_data ON (
				-- As noted in data-integrity.ipynb the address is sufficient here,
				-- despite mismatches in names.
				description.addr = function_data.address AND
				e2b.binary_id = function_data.binary_id
			)
		WHERE function_data.address IS NULL AND description.name_func NOT LIKE 'FUN_%'
	),
	-- Maps binary_id's to the infered image_base
	binary_id2image_base AS (
		SELECT f.binary_id, (ARRAY_AGG(DISTINCT d.addr - f.offset))[1] AS image_base
		FROM description_wo_function d
			JOIN "binary" b ON (
				d.binary_id = b.id
			)
			JOIN "function" f ON (
				d.name = f.name AND
				d.binary_id = f.binary_id
			)
		WHERE b.image_base = 0
		GROUP BY f.binary_id
		HAVING COUNT(DISTINCT d.addr - f.offset) = 1
	)
	SELECT b.id, b.name, b.md5, b.size, COALESCE(b2i.image_base, b.image_base) AS image_base, b.package_name, b.package_version, b.build_parameters_id
	FROM "binary" b
		LEFT OUTER JOIN binary_id2image_base b2i ON (
			b.id = b2i.binary_id
		)
);
CREATE INDEX ix_binary_id ON v.binary (id);
CREATE INDEX ix_binary_name ON v.binary (name);
CREATE INDEX ix_binary_md5 ON v.binary (md5);
CREATE INDEX ix_binary_size ON v.binary (size);
CREATE INDEX ix_binary_image_base ON v.binary (image_base);
CREATE INDEX ix_binary_package_name ON v.binary (package_name);
CREATE INDEX ix_binary_package_version ON v.binary (package_version);
CREATE INDEX ix_binary_build_parameters_id ON v.binary (build_parameters_id);

-- Maps ghidra description id's to functions.
-- Takes ~5 minutes for 20,000,000 entries in bsim.desctable
CREATE MATERIALIZED VIEW IF NOT EXISTS v.description2function AS (
	WITH function_data AS (
		SELECT f.id AS id, f.offset + b.image_base AS address, b.id AS binary_id, f.name
		FROM "function" AS f JOIN v.binary AS b ON f.binary_id = b.id
	)
	SELECT description.id AS description_id, function_data.id AS function_id, e2b.executable_id, e2b.binary_id
	FROM v.bsim_desctable AS description
		JOIN v.executable2binary e2b ON (
			description.id_exe = e2b.executable_id
		)
		JOIN function_data ON (
			-- As noted in data-integrity.ipynb the address is sufficient here,
			-- despite mismatches in names.
			description.addr = function_data.address AND
			e2b.binary_id = function_data.binary_id
		)
);
CREATE INDEX IF NOT EXISTS ix_description2function_description_id ON v.description2function (description_id);
CREATE INDEX IF NOT EXISTS ix_description2function_function_id ON v.description2function (function_id);
CREATE INDEX IF NOT EXISTS ix_description2function_binary_id ON v.description2function (binary_id);
CREATE INDEX IF NOT EXISTS ix_description2function_executable_id ON v.description2function (executable_id);

-- All binaries that could be mapped completely from ghidra to evaluatie.
-- Note that unnamed functions are left out.
CREATE MATERIALIZED VIEW v."binary:complete" AS (
	WITH description_wo_function AS (
		SELECT d.id, d.name_func AS name, d.id_exe AS executable_id
		FROM v.bsim_desctable d LEFT OUTER JOIN v.description2function d2f ON (
			d.id = d2f.description_id
		)
		WHERE d2f.description_id IS NULL
	),
	binary_w_missing_functions AS (
		SELECT DISTINCT e2b.binary_id AS id
		FROM description_wo_function d JOIN v.executable2binary e2b ON (
			d.executable_id = e2b.executable_id
		) JOIN "binary" b ON (
			b.id = e2b.binary_id
		)
		WHERE d.name NOT LIKE 'FUN_%'
	)
	SELECT b.*
	FROM v."binary" b
		LEFT OUTER JOIN binary_w_missing_functions bmissing ON (
			b.id = bmissing.id
		)
	WHERE bmissing.id IS NULL
);
CREATE INDEX "ix_binary:complete_id" ON v."binary:complete" (id);
CREATE INDEX "ix_binary:complete_name" ON v."binary:complete" (name);
CREATE INDEX "ix_binary:complete_md5" ON v."binary:complete" (md5);
CREATE INDEX "ix_binary:complete_size" ON v."binary:complete" (size);
CREATE INDEX "ix_binary:complete_image_base" ON v."binary:complete" (image_base);
CREATE INDEX "ix_binary:complete_package_name" ON v."binary:complete" (package_name);
CREATE INDEX "ix_binary:complete_package_version" ON v."binary:complete" (package_version);
CREATE INDEX "ix_binary:complete_build_parameters_id" ON v."binary:complete" (build_parameters_id);

-- All edges in the call-graph.
-- Note that this only contains functions that are found by ghidra and evaluatie,
-- which implies that dst_binary_id = src_binary_id.
-- Takes about 2min on my laptop.
CREATE TABLE v.call_graph_edge AS (
	SELECT src.function_id AS src_id, src.binary_id AS src_binary_id, dst.function_id AS dst_id, dst.binary_id AS dst_binary_id
	FROM v.bsim_callgraphtable bcg
		JOIN v.description2function src ON (
			src.description_id = bcg.src
		)
		JOIN v.description2function dst ON (
			dst.description_id = bcg.dest
		)
)
CREATE INDEX "ix_call_graph_edge_src_id" ON v.call_graph_edge (src_id);
CREATE INDEX "ix_call_graph_edge_dst_id" ON v.call_graph_edge (dst_id);
CREATE INDEX "ix_call_graph_edge_src_binary_id" ON v.call_graph_edge (src_binary_id);
CREATE INDEX "ix_call_graph_edge_dst_binary_id" ON v.call_graph_edge (dst_binary_id);
```

Now lets create some non-materialized views for queries that are quite fast and not that big.

```sql
-- All call-graph edges of binaries that are complete.
CREATE VIEW v."call_graph_edge:complete" AS (
	SELECT cg.*
	FROM v.call_graph_edge cg
		LEFT JOIN v."binary:complete" b ON (
			-- This is correct due to src_binary_id = dst_binary_id
			b.id = cg.src_binary_id
		)
)
```

```sql
SELECT lsh_reload();

-- All functions that are relevant in the evaluation
-- Takes 3 seconds for 50,000 vectors
CREATE MATERIALIZED VIEW "eval-function" AS
SELECT f.*
FROM "function" f JOIN "binary" b ON (
	f.binary_id = b.id
)
WHERE
-- See helper/filter_functions.py in tiknib
f.file IS NOT NULL AND
f.file LIKE ('%' || b.package_name || '%') AND
f.name NOT LIKE 'sub_%' AND
f.lineno IS NOT NULL AND
-- Functions without any vector are not interesting to us
f.vector IS NOT NULL

CREATE INDEX IF NOT EXISTS ix_eval_function_binary_id ON "eval-function" (binary_id);
CREATE INDEX IF NOT EXISTS ix_eval_function_file ON "eval-function" (file);
CREATE INDEX IF NOT EXISTS ix_eval_function_id ON "eval-function" (id);
CREATE INDEX IF NOT EXISTS ix_eval_function_lineno ON "eval-function" (lineno);
CREATE INDEX IF NOT EXISTS ix_eval_function_name ON "eval-function" (name);
-- XXX Some indices from "functio" are missing here
```


### Synchronizing Vectors
As insertions turn out to be kind of slow, so we just insert what is needed.
Note that this is a workaround and is most probably a symtom of poor database configuration.

```sql
-- Generate a table that contains all the binary id's that are interesting
WITH binary_ids AS (
	-- For now, let's take all the binaries that are actually analyzed
	SELECT DISTINCT binary_id AS id
	FROM "eval-function"
)
INSERT INTO call_graph_edge(src_id, dst_id)
SELECT src.function_id AS src_id, dst.function_id AS dst_id
FROM "function" f
	-- First filter the functions as they are the major bottleneck.
	-- The result is the set of functions that are in the relevant binaries.
	JOIN binary_ids ON (
		f.binary_id = binary_ids.id
	)
	JOIN description2function dst ON (dst.function_id = f.id)
	-- As the table is the set of all functions, all edges can be identfied
	-- by their end.
	JOIN bsim_callgraphtable cg ON (dst.description_id = cg.dest)
	JOIN description2function src ON (src.description_id = cg.src)
-- Ignore already inserted edges
ON CONFLICT DO NOTHING;



```



To synchronize the vectors from the studeerwerk database to the evaluatie database,
use the following sql:
```sql
-- Reload weights first. If we do not do this, the weights will all be set to zero.
-- The problem seems to be that `lsh_calc_weights` is not called.
SELECT lsh_reload();

-- Update weights for all vectors.
-- OPTIONAL
-- UPDATE "function"
-- SET vector = lshvector_in(lshvector_out(vector))
-- WHERE vector IS NOT NULL;


-- Update vector entries for all functions that have a corresponding function in Ghidra.
-- Imports 50,000 vectors into a set of 33,000,000 functions in one minute.
UPDATE "function" AS f
	SET vector = function_id2vector.vector
FROM (
	SELECT description2function.function_id, vectable.vec AS vector
	FROM bsim_vectable AS vectable JOIN bsim_desctable AS description ON (
			description.id_signature = vectable.id
		) JOIN description2function ON (
			description2function.description_id = description.id
		)
) AS function_id2vector
WHERE function_id2vector.function_id = f.id
```
