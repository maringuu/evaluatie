-- How we sample known positives:
--
-- How we sample known negatives:
-- Note that it does not make sense to pick functions from different programs,
-- as neighbsim is defined to work only on the same program.
--
-- General remarks:
-- We should definitly evaluate small functions separatly. Because they can
-- contain the same logic despite being defined multiple times.
--
-- Sampling should happen for each binary. Otherwise our evaluation is skewed 

function_count = 1000
functions_per_binary = 100
binaries = function_count / functions_per_binary

-- First, sample the software to be used.
-- Note that there are 232 softwares in total
WITH binaries AS (
	SELECT DISTINCT b.name, b.package_name, b.package_version
	FROM "binary" b
	WHERE EXISTS (
		SELECT *
		FROM "eval-function" f
		WHERE f.binary_id = b.id
	)
)
SELECT *
FROM binaries
ORDER BY RANDOM()
LIMIT 10

-- Now, for each software sample pairs of binaries to be compared.
-- We do this in order to avoid a bias against big binaries in our evaluation.
-- Arguably, this still has a bias (it is uniform in our existing data) but that is okay,
-- since we argue why our data is good. Further, this contains the maximum variance of sofware,
-- which is nice.
WITH b AS (
	-- All binaries from a specific software package
	SELECT *
	FROM "binary"
	WHERE (
		"name" = 'objdump' AND
		package_name = 'binutils' AND
		package_version = '2.30'
	) AND EXISTS (
		SELECT *
		FROM "eval-function"
		WHERE binary_id = "binary".id
	)
),
bin AS (
	-- Binaries with their build parameters
	SELECT qb.*, qbp.compiler_backend, qbp.compiler_version, qbp.optimisation, qbp.architecture, qbp.bitness, qbp.lto, qbp.noinline, qbp.pie
	FROM b AS qb JOIN build_parameters qbp ON (
		qb.build_parameters_id = qbp.id
	)
),
pair AS (
	-- Pairs of binaries that differ according to the requirements
	SELECT qb.id AS qb_id, tb.id AS tb_id
	FROM bin AS qb JOIN bin AS tb ON (
		qb.compiler_backend = tb.compiler_backend AND
		qb.compiler_version = tb.compiler_version AND
		qb.optimisation != tb.optimisation AND
		qb.architecture != tb.architecture AND
		qb.bitness = tb.bitness AND
		qb.lto = tb.lto AND
		qb.noinline = tb.noinline AND
		qb.pie = tb.pie AND
		-- Avoid having the same pair twice
		qb.id < tb.id
	)
),
fpair AS (
	-- Pairs of binaries with a query function for each pair.
	SELECT qb_id, tb_id, qf.id AS qf_id, qf.name AS qf_name, qf.file AS qf_file, qf.lineno AS qf_lineno
	FROM pair JOIN "eval-function" qf ON (
		qb_id = qf.binary_id
	)
	ORDER BY RANDOM()
    -- This is the number of pairs that we actually want.
    -- Note that there must not be a corresponding target function for every query function
	LIMIT 1000
)
-- Finally, select pairs of functions
SELECT DISTINCT ON (qb_id, tb_id, qf_id) qb_id, tb_id, qf_id, tf.id AS tf_id
FROM fpair JOIN "eval-function" tf ON (
		tb_id = tf.binary_id AND (
			tf.name = qf_name AND
			tf.file = qf_file AND
			tf.lineno = qf_lineno
		)
	)
ORDER BY qb_id, tb_id, qf_id, RANDOM()

-- Alternative, might be slower but actually always gives the correct amount of rows


WITH b AS (
	-- All binaries from a specific software package
	SELECT *
	FROM "binary"
	WHERE (
		"name" = 'objdump' AND
		package_name = 'binutils' AND
		package_version = '2.30'
	) AND EXISTS (
		SELECT *
		FROM "eval-function"
		WHERE binary_id = "binary".id
	)
),
bin AS (
	-- Binaries with their build parameters
	SELECT qb.*, qbp.compiler_backend, qbp.compiler_version, qbp.optimisation, qbp.architecture, qbp.bitness, qbp.lto, qbp.noinline, qbp.pie
	FROM b AS qb JOIN build_parameters qbp ON (
		qb.build_parameters_id = qbp.id
	)
),
pair AS (
	-- Pairs of binaries that differ according to the requirements
	SELECT qb.id AS qb_id, tb.id AS tb_id
	FROM bin AS qb JOIN bin AS tb ON (
		qb.compiler_backend = tb.compiler_backend AND
		qb.compiler_version = tb.compiler_version AND
		qb.optimisation != tb.optimisation AND
		qb.architecture != tb.architecture AND
		qb.bitness = tb.bitness AND
		qb.lto = tb.lto AND
		qb.noinline = tb.noinline AND
		qb.pie = tb.pie AND
		-- Avoid having the same pair twice
		qb.id < tb.id
	)
),
fpair AS (
	-- Pairs of binaries with a query function for each pair.
	SELECT qb_id, tb_id, qf.id AS qf_id, tf.id AS tf_id
	FROM pair JOIN "eval-function" qf ON (
		qb_id = qf.binary_id
	) JOIN "eval-function" tf ON (
		tb_id = tf.binary_id AND (
			tf.name = qf.name AND
			tf.file = qf.file AND
			tf.lineno = qf.lineno
		)
	)
	ORDER BY RANDOM()
    -- This is the number of pairs that we actually want.
    -- Note that there must not be a corresponding target function for every query function
	LIMIT 1000
)
SELECT *
FROM fpair
