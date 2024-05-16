<!--
SPDX-FileCopyrightText: 2024 Marten Ringwelski
SPDX-FileContributor: Marten Ringwelski <git@maringuu.de>

SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Evaluatie - Code for the Evaluation of my Master's Thesis
This repository contains a python module and accompanying jupyter notebooks.

## Installation
Use `evaluatie-initdb` to initalize the postgres databse.

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
UPDATE "function" SET vector = bsim_functions.vector
FROM (
    -- Update from all functions that are in Ghidra's tables.
    SELECT bsim.desctable.name_func AS function_name, bsim.exetable.md5 AS md5, bsim.vectable.vec AS vector
    FROM bsim.desctable
    JOIN bsim.vectable ON bsim.desctable.id_signature = bsim.vectable.id
    JOIN bsim.exetable ON bsim.desctable.id_exe = bsim.exetable.id
) AS bsim_functions
-- Update only functions in the exact same binary.
WHERE "function".vector IS NULL AND
    "function"."name" = bsim_functions.function_name AND
    "function".binary_id = (
        SELECT "binary".id
        FROM "binary"
        WHERE "binary".md5 = bsim_functions.md5
    );

```

## Notes
XXX Move these to docs
```sql
-- Copying tables
TRUNCATE idflookup;
INSERT INTO idflookup
SELECT * FROM bsim.idflookup;
```

```sql
-- Prewarm as the Ghidra code suggests
CREATE EXTENSION IF NOT EXISTS pg_prewarm;
SELECT pg_prewarm('function_vector_idx','read');
SELECT pg_prewarm('function','read');
```


```sql
-- Similarity scores of all function pairs that are semantically equal.
SELECT
    (lshvector_compare(function_1.vector, function_2.vector)).sim AS sim,
    function_1.name,
    function_2.name AS name_1,
    function_1.id,
    function_2.id,
    function_1.vector,
    function_2.vector
FROM
    function AS function_1
    JOIN "binary" AS binary_1 ON binary_1.id = function_1.binary_id
    JOIN function AS function_2 ON function_1.binary_id != function_2.binary_id
    JOIN "binary" AS binary_2 ON binary_2.id = function_2.binary_id
WHERE
    binary_1.package_name = binary_2.package_name
    AND binary_1.package_version = binary_2.package_version
    AND function_1.name = function_2.name
    AND function_1.file = function_2.file
    AND function_1.lineno = function_2.lineno
    AND function_1.vector IS NOT NULL
    AND function_2.vector IS NOT NULL
    AND function_1.binary_id != function_2.binary_id;
```

```sql
-- Debugging lshvector plugin
SELECT lshvector_compare('(1:582bcf95,1:d5574099)', '(1:582bcf95,1:d5574099)');

SELECT lsh_reload();

SELECT f1.id, lshvector_compare(f1.vector, f1.vector)
FROM "function" AS f1
WHERE f1.vector::varchar = '(1:582bcf95,1:d5574099)'
    AND f1.id = 1785;


-- As expected, this returns infinity
SELECT lshvector_compare(f1.vector, f2.vector)
FROM "function" AS f1, "function" AS f2
WHERE f1.id = 1785 AND f2.id = 16737;

-- This reliably makes all comparisons return nan
UPDATE "function"
SET vector = lshvector_in(lshvector_out(vector))
WHERE vector IS NOT NULL;
```

```sh
# Backup the bsim database (data only)
pg_dump \
    --format=tar \
    --schema=public \
    --dbname=bsim \
> /tmp/bsim.tar

# Copy from container to host
docker cp studeerwerk-postgres:/tmp/bsim.tar bsim.tar

# Copy from host to container
docker cp bsim.tar studeerwerk-postgres:/tmp/bsim.tar

# Restore the database
pg_restore \
    --format=tar \
    --schema=public \
    --dbname=bsim \
< /tmp/bsim.tar
```


```sh
# Creating a postgres instance that can be debugged.

# Install the lshvector plugin
# Append -g and -O0 to allow debugging.
CFLAGS="$(pg_config --cflags) -g -O0"
doas make \
    -C lshvector \
    -f Makefile.lshvector \
    PG_CONFIG=/usr/bin/pg_config \
    CFLAGS="$CFLAGS" \
install

pg_data=~/tmp/studeerwerk-pg_data/
mkdir $pg_data
# No need to enable ssl here, as we restore the database anyways.
initdb -D $pg_data \
    --set "unix_socket_directories=$XDG_RUNTIME_DIR"

pg_ctl \
    -D $pg_data \
    start

# Now use pg_restore to add data to the database
psql \
    --host="$XDG_RUNTIME_DIR" \
    --dbname=postgres

# First restore the bsim database.
CREATE DATABASE bsim;
\c bsim;
CREATE EXTENSION lshvector;
\password maringuu

# Do not use ghidras initdb here as it requires ssl.
# The table definitions are already in the databse dump.
gunzip -c tests/data/bsim.tar.gz | \
pg_restore \
    --format=tar \
    --schema=public \
    --dbname=bsim \
    --host $XDG_RUNTIME_DIR


# Now restore the evaluatie database.
CREATE DATABASE evaluatie;
\c evaluatie;
\password maringuu

./evaluatie-initdb \
    --postgres-url postgresql://maringuu:maringuu@localhost:5432/evaluatie

# Data only, as the tables were just created using evalautie-initdb
# Disabe triggers to avoid errors with the build_parameters table.
gunzip -c tests/data/evaluatie.tar.gz | \
pg_restore \
    --format=tar \
    --schema=public \
    --dbname=evaluatie \
    --data-only \
    --disable-triggers \
    --host $XDG_RUNTIME_DIR
```

```sh
# Some helpful gdb commands for degugging vector weights

# Print vector items
p a->items@a->numitems
```

