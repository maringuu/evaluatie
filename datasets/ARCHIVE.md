# Archive -- Unused SQL Code.
Over time, I have written a lot of sql.
Ideally, no code would be lost since it was at some time tracked by git.
Due to time contstraints I rarely have time to keep a proper git history
in this project.
Ultimatly, this leads to the creation of this file: An archive of code snippets
I do not want to throw away.

```sql
-- Takes roughly 2.5minutes for 33mio functions
-- We are not doing this!
CREATE TABLE d.factors AS (
    WITH tbl AS (
        SELECT
            fctr.*,
            ROW_NUMBER() OVER (
                PARTITION BY (
                    fctr.optimisation,
                    fctr.architecture,
                    fctr.bitness,
                    fctr.noinline,
                    fctr.package,
                    fctr.size,
                    fctr.complexity,
                    fctr.neighborhood_size
                ) ORDER BY fctr.random_id
            ) as sample_number
        FROM e."factors" fctr
    )
    SELECT tbl.*
    FROM tbl
    -- Sample this amount of functions per partition
    WHERE sample_number <= 5
    ORDER BY (
        tbl.optimisation,
        tbl.architecture,
        tbl.bitness,
        tbl.noinline,
        tbl.package,
        tbl.size,
        tbl.complexity,
        tbl.neighborhood_size,
        tbl.random_id
    )
);

CREATE MATERIALIZED VIEW e."binary:complete" AS (
    SELECT b.*
    FROM e.binary b
        JOIN v."binary:complete" bc ON (
            b.id = bc.id
        )
);
CREATE INDEX ON e."binary:complete" (id);
CREATE INDEX ON e."binary:complete" (name);
CREATE INDEX ON e."binary:complete" (md5);
CREATE INDEX ON e."binary:complete" (size);
CREATE INDEX ON e."binary:complete" (image_base);
CREATE INDEX ON e."binary:complete" (package_name);
CREATE INDEX ON e."binary:complete" (package_version);
CREATE INDEX ON e."binary:complete" (build_parameters_id);


```
