# SPDX-FileCopyrightText: 2024 Marten Ringwelski
# SPDX-FileContributor: Marten Ringwelski <git@maringuu.de>
#
# SPDX-License-Identifier: AGPL-3.0-only

import dataclasses
import enum

import sqlalchemy as sa
import sqlalchemy.orm
import sqlalchemy_utils as sau
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from evaluatie import cfg

engine = sa.create_engine(
    cfg.gets("evaluatie", "postgres-url"),
    echo=False,
)
Session = sa.orm.sessionmaker(engine)


class LshVector(sa.types.UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw):
        _ = kw
        return "lshvector"


@sa.event.listens_for(sa.Engine, "engine_connect")
def on_engine_connect(conn: sa.Connection):
    # From the extension's source code:
    # > typedef struct
    # > {
    # >   uint32 hash;			/* A specific hash */
    # >   uint16 tf;			/* Associated hash(term) frequency */
    # >   uint16 idf;			/* Inverse Document Frequency */
    # >   double coeff;			/* The actual weight of this hash as a coefficient */
    # > } LSH_ITEM;
    #
    # Somehow the idflookup table is not loaded (despite it being loaded via `lsh_load`
    # on plugin initalisation).
    # This is not a problem for vectors from rows, since they seem to be stored
    # with their coefficients (coeff in struct LSH_ITEM). Vectors loaded
    # via lshvector_in do not have the coefficients loaded. Furthermore,
    # the tf is always one and the idf is always zero.
    # This can be worked around by (re)loading the table in the respective process,
    # which is why this is done on connection level.

    # Somehow we need an appropiate (nested) transaction to avoid rollbacks.
    begin = conn.begin_nested if conn.in_transaction() else conn.begin
    with begin() as transaction:
        # Somehow this has to be inside a separate transaction.
        # Otherwise all transaction are rolled back.
        conn.execute(sa.text("SELECT lsh_reload();"))
        transaction.commit()


class Architecture(enum.Enum):
    pass


class Compiler(enum.Enum):
    GCC = "gcc"
    CLANG = "clang"


class Base(DeclarativeBase):
    pass


@sau.generic_repr
class BuildParameters(Base):
    __tablename__ = "build_parameters"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )
    #: The used compiler. Either 'gcc' or 'clang'.
    compiler_backend: Mapped[str] = mapped_column()
    #: The compilers version
    compiler_version: Mapped[str] = mapped_column()
    #: The chose optimisation level.
    #: One of 'O0', 'O1', 'O2', 'O3', 'Os'
    optimisation: Mapped[str] = mapped_column()
    #: The binary's architecture
    architecture: Mapped[str] = mapped_column()
    #: The architectures bitness
    bitness: Mapped[int] = mapped_column()
    #: Whether the binary was compiled with link-time optimisation
    lto: Mapped[bool] = mapped_column()
    # XXX There is no option to disable inlining in gcc
    noinline: Mapped[bool] = mapped_column()
    #: Whether the binary was compiled with '-fPIE'
    pie: Mapped[bool] = mapped_column()

    __table_args__ = (
        sa.UniqueConstraint(
            compiler_backend,
            compiler_version,
            optimisation,
            architecture,
            bitness,
            lto,
            noinline,
            pie,
        ),
    )


@dataclasses.dataclass
class Package:
    #: The package's name
    name: str
    #: The package's version
    version: str


@sau.generic_repr
class Binary(Base):
    __tablename__ = "binary"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )
    #: The binary's name
    name: Mapped[str] = mapped_column(
        index=True,
    )
    #: The binary's md5 hash
    md5: Mapped[str] = mapped_column(
        index=True,
    )
    #: The binary's size in bytes
    size: Mapped[int] = mapped_column(
        index=True,
    )
    #: The binary's base addrees (cf. ld(1) and objdump -p)
    image_base: Mapped[int] = mapped_column(
        sa.BigInteger,
    )

    package_name: Mapped[str] = mapped_column(
        "package_name",
        index=True,
    )
    package_version: Mapped[str] = mapped_column(
        "package_version",
        index=True,
    )
    package: Mapped[Package] = sa.orm.composite(
        Package,
        package_name,
        package_version,
    )

    build_parameters_id: Mapped[int] = mapped_column(
        sa.ForeignKey("build_parameters.id"),
        index=True,
    )
    build_parameters: Mapped[BuildParameters] = relationship()
    functions: Mapped[list["Function"]] = relationship(
        back_populates="binary",
    )

    @hybrid_property
    def hid(self) -> str:
        """Returns a human readable identifier for the binary."""
        # fmt: off
        return (
            self.package_name
            # Ghidra does not allow colons in program names, thus we use a dot.
            + "."
            + self.name
            + "."
            + self.package_version
            + "."
            + self.md5
        )
        # fmt: on

    __table_args__ = (
        sa.UniqueConstraint(
            package_name,
            name,
            package_version,
            md5,
            name="hid_unique",
        ),
    )


@sau.generic_repr
class Function(Base):
    __tablename__ = "function"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    #: The functions demangled name (Should match the name in the source code)
    name: Mapped[str] = mapped_column(
        index=True,
    )
    #: The path to the source file that this funciton is defined in.
    file: Mapped[str] = mapped_column(
        # Nullable to account for missing data
        nullable=True,
        index=True,
    )
    path: Mapped[str] = mapped_column(
        nullable=True,
        index=True,
    )
    #: The line number of the function in the source file.
    lineno: Mapped[int] = mapped_column(
        # Nullable to account for missing data
        nullable=True,
        index=True,
    )

    #: The offset in the file
    offset: Mapped[int] = mapped_column()
    #: The function's size in bytes
    size: Mapped[int] = mapped_column()
    #: The functions section in the binary
    section: Mapped[str] = mapped_column()

    binary_id: Mapped[int] = mapped_column(
        sa.ForeignKey("binary.id"),
        index=True,
    )
    binary: Mapped[Binary] = relationship(
        back_populates="functions",
    )
    vector = mapped_column(
        LshVector,
        # Nullable to account for functions that Ghidra did not find
        nullable=True,
    )
    features_id: Mapped[int] = mapped_column(
        sa.ForeignKey("features.id"),
        index=True,
        unique=True,
    )
    features: Mapped["Features"] = relationship(
        foreign_keys=features_id,
    )


    __table_args__ = (
        # Ensure that function names are unique in a gesingle binary.
        sa.UniqueConstraint(
            "name",
            binary_id,
        ),
        # Used for comparing two functions.
        sa.Index(
            "function_equal_idx",
            id,
            name,
            file,
            lineno,
            binary_id,
        ),
        # Locality sensitive hashing index for vector column
        # Same as the index in Ghidra's 'vectable'.
        sa.Index(
            "function_vector_idx",
            vector,
            postgresql_using="gin",
            postgresql_ops={
                "vector": "gin_lshvector_ops",
            },
        ),
    )

class Features(Base):
    """Manually engineered features of functions.
    Note that the destinction of this table and the 'function' table
    is not clear. On could say that this table contains less essential
    features while the function table contains features that are necessary
    to describe a function."""
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    cfg_node_count: Mapped[int] = mapped_column(
        index=True,
    )
    cfg_edge_count: Mapped[int] = mapped_column(
        index=True,
    )
    # XXX This is missing the section name and hash
