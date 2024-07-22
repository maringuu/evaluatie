import pathlib as pl

import msgspec
import pandas as pd


class DatasetOptions(msgspec.Struct):
    size: str | None = None
    neighborhood_size: str | None = None

    def indexer(self, frame: pd.DataFrame):
        ret = pd.Series(
            data=True,
            index=frame.index,
        )
        if self.size is not None and self.size != "all":
            ret &= frame["qsize"] == self.size
        if self.neighborhood_size is not None and self.neighborhood_size != "all":
            ret &= frame["qneighborhood_size"] == self.neighborhood_size

        return ret


class FunctionDataset(msgspec.Struct):
    name: str
    frame: pd.DataFrame

    @classmethod
    def from_name(cls, name: str):
        csv_path = pl.Path("datasets", f"{name}.csv")
        if not csv_path.exists():
            raise ValueError(f"The dataset {name} was expected at {csv_path} but not found.")

        csv_frame = pd.read_csv(csv_path)
        csv_frame = _massage_frame(csv_frame)
        return cls(
            name=name,
            frame=csv_frame,
        )

    def load_pickle(self) -> "FunctionDataset":
        if "neighbsim" in self.frame:
            raise ValueError("Pickle is already loaded")

        pickle_path = pl.Path("datasets", f"{self.name}.pickle.gz")
        if not pickle_path.exists():
            raise ValueError(
                f"The dataset {self.name} was expected at {pickle_path} but not found."
            )

        pickle_frame = pd.read_pickle(pickle_path)

        return FunctionDataset(
            name=self.name,
            frame=pd.concat(
                [
                    self.frame,
                    pickle_frame,
                ],
                ignore_index=False,
                axis=1,
            ),
        )

    def dropna(self) -> "FunctionDataset":
        return FunctionDataset(
            name=self.name,
            frame=self.frame.dropna(),
        )


def _massage_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.drop(
        columns="sample_number",
        axis=1,
    )
    frame["noinline"] = frame["noinline"].map({"t": True, "f": False})
    # Replace na scores with zero scores.
    # Ideally, this does not happen, as both vectors should not be null
    # since they are sourced from e.functions
    # In the real world this seems to happen. Dunno why.
    frame["pscore"] = frame["pscore"].fillna(value=0)
    frame["nscore"] = frame["nscore"].fillna(value=0)

    # Add a 'label' row and have only a single target_function_id
    value_vars = [
        "ntarget_function_id",
        "ptarget_function_id",
    ]
    frame = frame.melt(
        id_vars=[column for column in frame.columns if column not in value_vars],
        value_vars=value_vars,
    ).rename(
        {
            "variable": "label",
            "value": "target_function_id",
        },
        axis=1,
    )
    frame["label"] = frame["label"] == "ptarget_function_id"

    # Add target function factors
    for column in [
        "score",
        "size",
        "complexity",
        "neighborhood_size",
    ]:
        frame.loc[frame["label"] == 1, f"t{column}"] = frame[f"p{column}"]
        frame.loc[frame["label"] == 0, f"t{column}"] = frame[f"n{column}"]
        frame = frame.drop(
            columns=[
                f"p{column}",
                f"n{column}",
            ]
        )

    frame = frame.rename({"tscore": "bsim"}, axis=1)

    return frame

class BinaryDataset(msgspec.Struct):
    """Pairs of biaries"""
    name: str
    frame: pd.DataFrame

    @classmethod
    def from_name(cls, name: str):
        csv_path = pl.Path("datasets", f"{name}.csv")
        if not csv_path.exists():
            raise ValueError(f"The dataset {name} was expected at {csv_path} but not found.")

        csv_frame = pd.read_csv(csv_path)
        return cls(
            name=name,
            frame=csv_frame,
        )
