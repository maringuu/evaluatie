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
work_mem = 2GB
max_wal_size = 2GB
# Increase the maximum connections to allow many inserts at once.
max_connections = 256
# Makes our life easier when connecting from other containers
listen_addresses = '*'
```

### Creating Views
To allow postgres to do fast queries on foreign tables, we use materialized views with custom indices.
All views are created in a separate schema.

```sql
-- 'v' is short for 'view'. It empathises that this is not the
-- data created by the evaluatie python module.
-- It contains exactly the data from bsim and evaluatie.
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
    SELECT b.id,
        b.name,
        b.md5,
        b.size,
        CASE WHEN b.image_base = 0 AND bp.bitness = 32 THEN 65536
             WHEN b.image_base = 0 AND bp.bitness = 64 THEN 1048576
             ELSE b.image_base
        END AS image_base,
        b.package_name,
        b.package_version,
        b.build_parameters_id
    FROM "binary" b
        JOIN build_parameters bp ON (
            bp.id = b.build_parameters_id
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
-- So for every function that ghidra found, there is a function in the evaluatie set.
-- The reverse is not nececarrily true.
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
);
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

SELECT lsh_reload();

-- A table of all functions that we want in our evaluation. Features are not included.
-- See the v."factors" view .
CREATE MATERIALIZED VIEW v."function:eval" AS (
	SELECT f.*
	FROM "function" f
		-- Since we can only actually evaluate functions that have a vector associtated
		-- we do an inner join with the description2function mapping.
		JOIN v.description2function d2f ON (
			f.id = d2f.function_id
		)
		JOIN "binary" b ON (
		 	b.id = f.binary_id
		)
	-- Finnally, we filter in the same manner as Kim et al.
	-- XXX: The section is missing here (but not that important since other papers did not do this).
	WHERE f.file IS NOT NULL AND
	f.file LIKE ('%' || b.package_name || '%') AND
	f.name NOT LIKE 'sub_%' AND
	f.lineno IS NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_eval_function_id ON v."function:eval" (id);
CREATE INDEX IF NOT EXISTS ix_eval_function_binary_id ON v."function:eval" (binary_id);
CREATE INDEX IF NOT EXISTS ix_eval_function_file ON v."function:eval" (file);
CREATE INDEX IF NOT EXISTS ix_eval_function_lineno ON v."function:eval" (lineno);
CREATE INDEX IF NOT EXISTS ix_eval_function_name ON v."function:eval" (name);
-- XXX Some indices from "functio" are missing here
```

### Creating evaluation subsets
While it is nice to have all data in the databse, we do not use it completely.
Thus, we create views that contain these subsets.
```sql
-- 'e' is show for 'evaluation'.
-- Contains subsets of the data that we actually use.
-- All tables are only subsets.
CREATE SCHEMA e;
```

```sql
-- All complete binaries using the correct compiler.
CREATE MATERIALIZED VIEW e.binary AS (
    SELECT b.*
    FROM v."binary:complete" b
        JOIN build_parameters bp ON (
            bp.id = b.build_parameters_id
        )
    WHERE bp.compiler_backend = 'gcc' AND bp.compiler_version = '8.2.0'
);
CREATE INDEX ix_binary_id ON e.binary (id);
CREATE INDEX ix_binary_name ON e.binary (name);
CREATE INDEX ix_binary_md5 ON e.binary (md5);
CREATE INDEX ix_binary_size ON e.binary (size);
CREATE INDEX ix_binary_image_base ON e.binary (image_base);
CREATE INDEX ix_binary_package_name ON e.binary (package_name);
CREATE INDEX ix_binary_package_version ON e.binary (package_version);
CREATE INDEX ix_binary_build_parameters_id ON e.binary (build_parameters_id);

-- A table with all functions.
-- We need this to calculate similarity graphs.
CREATE TABLE e."function:all" AS (
    SELECT f.*
    FROM "function" f
        JOIN e.binary b ON (
            f.binary_id = b.id
        )
);
CREATE INDEX ON e."function:all" (id);
CREATE INDEX ON e."function:all" (binary_id);
CREATE INDEX ON e."function:all" (name);
CREATE INDEX ON e."function:all" (lineno);
CREATE INDEX ON e."function:all" ("file");
CREATE INDEX ON e."function:all" ("offset");
CREATE INDEX ON e."function:all" ("size");
CREATE INDEX ON e."function:all" (features_id);


-- Make this a table, so we can import vectors in it.
-- Functions in this list must fulfill the following:
-- * Be part of a complete binary (Does not imply that the vector is null, as evalautie is a superset of ghidra functions)
-- * Be defined in the source code (i.e. have a non-null file)
-- * be in the .text section
-- * be part of the specified package
CREATE TABLE e.function AS (
    -- As the original paper, filter out duplicate functions per package and compile options.
    -- Note that this also filters out multiple instanciations of the same function (again as the original paper)
    SELECT DISTINCT ON (b.package_name, b.build_parameters_id, f.file, f.name, f.lineno)
        f.*
    FROM "function" f
        -- Join binaries to filter out non-complete binaries
        JOIN e.binary b ON (
            f.binary_id = b.id
        )
    WHERE f.file IS NOT NULL
        AND f.section = '.text'
        AND f.path LIKE ('%' || b.package_name || '%')
        AND f.name NOT LIKE 'FUN_%'
    -- Select an isntanciation at random if there are multiple
    ORDER BY b.package_name, b.build_parameters_id, f.file, f.name, f.lineno, RANDOM()
);
-- Delete functions from binaries that only have one function in them.
-- These functions are non-sensical for selecting negative pairs, thus we remove them.
WITH fns AS (
    -- This must be the same condidtion as above.
	SELECT f.*
	FROM "function" f
		-- Join binaries to filter out non-complete binaries
		JOIN e.binary b ON (
			f.binary_id = b.id
		)
	WHERE f.file IS NOT NULL
		AND f.section = '.text'
		AND f.path LIKE ('%' || b.package_name || '%')
		AND f.name NOT LIKE 'FUN_%'
), bs AS (
	SELECT fns.binary_id
	FROM fns
	GROUP BY fns.binary_id
	HAVING COUNT(fns.id) = 1
), bnames AS (
	SELECT DISTINCT b.name
    FROM bs
	JOIN e.binary b ON (
		bs.binary_id = b.id
	)
)
DELETE FROM e.function f
WHERE f.id IN (
	SELECT g.id
	FROM e.function g
		JOIN e.binary b ON (
			g.binary_id = b.id
		)
	WHERE b.name IN (SELECT * FROM bnames)
);


CREATE INDEX ON e.function (id);
CREATE INDEX ON e.function (binary_id);
CREATE INDEX ON e.function (name);
CREATE INDEX ON e.function (lineno);
CREATE INDEX ON e.function ("file");
CREATE INDEX ON e.function ("offset");
CREATE INDEX ON e.function ("size");
CREATE INDEX ON e.function (features_id);
-- XXX vector index?

-- MUST be executed after importing the vectors
-- All functions of complete binaries, that ghidra found.
-- Takes 30 sedonds on my laptop.
CREATE MATERIALIZED VIEW e."function:ghidra" AS (
    SELECT f.*
    FROM e.function f
        JOIN v.description2function d2f ON (
            f.id = d2f.function_id
        )
    WHERE f.vector IS NOT NULL
);
CREATE INDEX ON e."function:ghidra" (id);
CREATE INDEX ON e."function:ghidra" (binary_id);
CREATE INDEX ON e."function:ghidra" (name);
CREATE INDEX ON e."function:ghidra" (lineno);
CREATE INDEX ON e."function:ghidra" ("file");
CREATE INDEX ON e."function:ghidra" ("offset");
CREATE INDEX ON e."function:ghidra" ("size");
CREATE INDEX ON e."function:ghidra" (features_id);

CREATE MATERIALIZED VIEW e.features AS (
    SELECT ft.*
    FROM features ft
        JOIN e.function f ON (
            f.features_id = ft.id
        )
);
CREATE INDEX ON e.features (id);
CREATE INDEX ON e.features (cfg_node_count);
CREATE INDEX ON e.features (cfg_edge_count);

CREATE MATERIALIZED VIEW e.call_graph_edge AS (
    SELECT cg.*
    FROM v.call_graph_edge cg
        JOIN e.binary b ON (
            cg.src_binary_id = b.id
        )
);
CREATE INDEX ON e.call_graph_edge (src_id);
CREATE INDEX ON e.call_graph_edge (dst_id);
CREATE INDEX ON e.call_graph_edge (src_binary_id);
CREATE INDEX ON e.call_graph_edge (dst_binary_id);

-- Takes about one minute
CREATE MATERIALIZED VIEW e."factors:raw" AS (
    WITH callers AS (
        SELECT f.id AS function_id, COUNT(incoming.src_id) AS "count"
        FROM e.function f
            LEFT JOIN e.call_graph_edge incoming ON (
                incoming.dst_id = f.id
            )
        GROUP BY f.id
    ),
    callees AS (
        SELECT f.id AS function_id, COUNT(outgoing.dst_id) AS "count"
        FROM e.function f
            LEFT JOIN e.call_graph_edge outgoing ON (
                outgoing.src_id = f.id
            )
        GROUP BY f.id
    )
    SELECT
        f.id AS function_id,
        ROW_NUMBER() OVER (ORDER BY RANDOM()) AS random_id,
        bp.optimisation,
        bp.architecture,
        bp.bitness,
        bp.noinline,
        b.package_name || '-' || b.package_version AS package,
        ft.cfg_node_count AS size,
        ft.cfg_edge_count - ft.cfg_node_count + 2 AS complexity,
        callees.count + callers.count AS neighborhood_size
    FROM e.function f
        JOIN e.binary b ON (
            b.id = f.binary_id
        )
        JOIN build_parameters bp ON (
            bp.id = b.build_parameters_id
        )
        JOIN features ft ON (
            ft.id = f.features_id
        )
        JOIN callers ON (
            f.id = callers.function_id
        )
        JOIN callees ON (
            f.id = callees.function_id
        )
);
CREATE INDEX ON e."factors:raw" (function_id);
CREATE INDEX ON e."factors:raw" (random_id);
CREATE INDEX ON e."factors:raw" (optimisation);
CREATE INDEX ON e."factors:raw" (architecture);
CREATE INDEX ON e."factors:raw" (bitness);
CREATE INDEX ON e."factors:raw" (noinline);
CREATE INDEX ON e."factors:raw" (package);
CREATE INDEX ON e."factors:raw" (size);
CREATE INDEX ON e."factors:raw" (complexity);
CREATE INDEX ON e."factors:raw" (neighborhood_size);
```

### Synchronizing Vectors
As insertions turn out to be kind of slow, so we just insert what is needed.
Note that this is a workaround and is most probably a symtom of poor database configuration.

To synchronize the vectors from the studeerwerk database to the evaluatie database,
use the following sql:
```sql
-- Update vector entries for all functions that have a corresponding function in Ghidra.
-- Imports 5,286,666 vectors into a set of 8,962,167 functions in 7 minutes.
-- Reload weights first. If we do not do this, the weights will all be set to zero.
-- The problem seems to be that `lsh_calc_weights` is not called.
SELECT lsh_reload();
UPDATE e."function" AS f
	SET vector = function_id2vector.vector
FROM (
	SELECT d2f.function_id, vectable.vec AS vector
	FROM v.bsim_vectable AS vectable JOIN v.bsim_desctable AS description ON (
			description.id_signature = vectable.id
		) JOIN v.description2function d2f ON (
			d2f.description_id = description.id
		)
) AS function_id2vector
WHERE function_id2vector.function_id = f.id;
-- Update the second table as well.
-- Note that while it is not guaranteed, that all of these functions will have a vector
-- (as it is a superset of the ghidra functions) all functions in the call-graph
-- are guaranteed to have a vector (as the call graph is sourced from ghidra)
UPDATE e."function:all" AS f
	SET vector = function_id2vector.vector
FROM (
	SELECT d2f.function_id, vectable.vec AS vector
	FROM v.bsim_vectable AS vectable JOIN v.bsim_desctable AS description ON (
			description.id_signature = vectable.id
		) JOIN v.description2function d2f ON (
			d2f.description_id = description.id
		)
) AS function_id2vector
WHERE function_id2vector.function_id = f.id;

-- Update weights if we forgot to use lsh_reload before.
SELECT lsh_reload();
-- This makes the code load the internal weights again.
UPDATE e."function" SET vector = (vector::text)::lshvector;
UPDATE e."function:all" SET vector = (vector::text)::lshvector;
```

