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



