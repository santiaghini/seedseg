from __future__ import annotations

import math
import os
from enum import Enum
from datetime import datetime
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from dataclasses import dataclass, field
from scipy.stats import chisquare

from config import TARGET_RATIO

VALID_EXTENSIONS: list[str] = [".tif", ".tiff", ".png", ".jpg", ".jpeg"]


class CountMethod(Enum):
    """Enumeration of counting methods."""

    FLUORESCENCE = "fluorescence"
    COLORIMETRIC = "colorimetric"


def plot_full(img: np.ndarray, title: str = "", cmap: str = "jet") -> None:
    plt.figure(figsize=(10, 10))
    plt.imshow(img, cmap)
    plt.axis("off")
    plt.title(title)
    plt.tight_layout()
    plt.show()


def plot_all(plots: list[tuple[np.ndarray, str, str | None]]) -> None:
    num_plots = len(plots)
    if num_plots == 0:
        return

    # Choose up to 3 columns for aesthetics, but you can change this
    max_cols = 3
    num_cols = min(num_plots, max_cols)
    num_rows = math.ceil(num_plots / num_cols)

    # Set figure size: 5x5 inches per subplot is a good default
    fig_width = 5 * num_cols
    fig_height = 5 * num_rows
    fig, axes = plt.subplots(num_rows, num_cols, figsize=(fig_width, fig_height))

    # If only one plot, axes is not an array
    if num_plots == 1:
        axes = np.array([axes])

    axes = axes.flatten()

    default_cmap = "jet"
    for ax, (image, title, cmap) in zip(axes, plots):
        cmap = cmap if cmap else default_cmap
        ax.imshow(image, cmap=cmap)
        ax.set_title(title)
        ax.axis("off")

    # Hide any unused subplots
    for ax in axes[num_plots:]:
        ax.axis("off")

    plt.tight_layout()
    plt.show()

    # Last plot is full screen (final result)
    plot_full(*plots[-1])


@dataclass
class Result:
    prefix: str
    marker_seeds: int | None = None
    total_seeds: int | None = None
    target_ratio: float = TARGET_RATIO
    bf_thresh: int | None = None
    marker_thresh: int | None = None
    radial_threshold: float | None = None
    radial_threshold_ratio: float | None = None

    def __repr__(self) -> str:
        return (
            f"Result(prefix={self.prefix!r}, "
            f"marker_seeds={self.marker_seeds!r}, "
            f"non_marker_seeds={self.non_marker_seeds!r}, "
            f"total_seeds={self.total_seeds!r}, "
            f"ratio_marker_total={self.ratio_marker_total!r}, "
            f"target_ratio={self.target_ratio!r}, "
            f"chisquare={self.chisquare!r}, "
            f"pvalue={self.pvalue!r}, "
            f"bf_thresh={self.bf_thresh!r}, "
            f"marker_thresh={self.marker_thresh!r}, "
            f"radial_threshold={self.radial_threshold!r},"
            f"radial_threshold_ratio={self.radial_threshold_ratio!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefix": self.prefix,
            "marker_seeds": self.marker_seeds,
            "non_marker_seeds": self.non_marker_seeds,
            "total_seeds": self.total_seeds,
            "ratio_marker_total": self.ratio_marker_total,
            "target_ratio": self.target_ratio,
            "chisquare": self.chisquare,
            "pvalue": self.pvalue,
            "bf_thresh": self.bf_thresh,
            "marker_thresh": self.marker_thresh,
            "radial_threshold": self.radial_threshold,
            "radial_threshold_ratio": self.radial_threshold_ratio,
        }

    @property
    def non_marker_seeds(self) -> int | None:
        if self.total_seeds and self.marker_seeds:
            return self.total_seeds - self.marker_seeds
        return None

    @property
    def ratio_marker_total(self) -> float | None:
        if self.total_seeds and self.marker_seeds:
            return self.marker_seeds / self.total_seeds
        return None

    @property
    def chisquare(self) -> float | None:
        if self.total_seeds and self.marker_seeds:
            _chisquare, _pvalue = compute_chi2(self, self.target_ratio)
            return _chisquare
        return None

    @property
    def pvalue(self) -> float | None:
        _chisquare, _pvalue = compute_chi2(self, self.target_ratio)
        return _pvalue


def compute_chi2(result: Result, expected_ratio: float) -> tuple[float, float]:
    """Return the chi-square statistic and p-value for a segregation test."""
    observed = np.array([result.marker_seeds, result.non_marker_seeds])
    total = result.total_seeds
    expected = np.array([expected_ratio, (1 - expected_ratio)]) * total
    chi2_result = chisquare(f_obs=observed, f_exp=expected)
    chi2, p = chi2_result
    return chi2, p


def build_results_csv(results: list[Result]) -> list[list[str | float | int | None]]:
    """Return CSV rows (including header) representing the batch ``results``."""
    print(f"results: {results}")
    col_names = [
        "sample",
        "marker_seeds",
        "non_marker_seeds",
        "total_seeds",
        "ratio_fl_total",
        "chisquare",
        "pvalue",
        "bf_intensity_thresh",
        "marker_intensity_thresh",
        "radial_threshold",
        "radial_threshold_ratio",
    ]
    rows = [col_names]
    for result in results:
        row = [
            result.prefix,
            result.marker_seeds,
            result.non_marker_seeds,
            result.total_seeds,
            round(result.ratio_marker_total, 2),
            round(result.chisquare, 4),
            round(result.pvalue, 4),
            round(result.bf_thresh, 2),
            round(result.marker_thresh, 2),
            round(result.radial_threshold, 2),
            round(result.radial_threshold_ratio, 2),
        ]
        rows.append(row)
    return rows


def round_if_not_none(num: float | int | None, decimals: int = 2) -> float | int | None:
    return round(num, decimals) if num is not None else None


def store_results(
    results: list[Result],
    batch_output_dir: str,
    batch_id: str | None = None,
    filename: str | None = None,
) -> str:
    """Write ``results`` to ``batch_output_dir`` and return the CSV path."""
    results_csv = build_results_csv(results)

    bf_thresh = results[0].bf_thresh
    marker_thresh = results[0].marker_thresh
    radial_ratio = results[0].radial_threshold_ratio

    # save file with current timestamp
    if not batch_id:
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not filename:
        filename = (
            f"results_{batch_id}_bfthresh={round(bf_thresh, 2) if bf_thresh is not None else bf_thresh}"
            f"_markerthresh={round(marker_thresh, 2) if marker_thresh is not None else marker_thresh}"
            f"_radialthresh={round(results[0].radial_threshold_ratio, 2) if results[0].radial_threshold_ratio is not None else results[0].radial_threshold_ratio}"
            f"_radialratio={round(radial_ratio, 2) if radial_ratio is not None else radial_ratio}.csv"
        )

    output_path = os.path.join(batch_output_dir, filename)

    os.makedirs(batch_output_dir, exist_ok=True)
    with open(output_path, "w") as f:
        for row in results_csv:
            f.write(",".join([f"{r}" for r in row]) + "\n")

    return output_path


def parse_filename(filename: str, bf_suffix: str, fl_suffix: str) -> tuple[str, str]:
    """Parse ``filename`` into ``(sample_name, image_type)``."""

    reminder = (
        f"Filenames must be in the format <sample_name>_<image_type_suffix>."
        f"<extension>. Example: VZ254_{bf_suffix}.tif"
    )
    try:
        pieces = filename.split(".")
        name = pieces[0]
        extension = pieces[-1]

        name_pieces = name.split("_")
        sample_name = "_".join(name_pieces[0:-1]) #new
        #sample_name = name_pieces[0] former
        img_type = name_pieces[-1]

    except Exception as e:
        print(e)
        raise Exception(f"Invalid filename: {filename}. {reminder}")

    if "." + extension not in VALID_EXTENSIONS:
        raise Exception(
            f"Invalid extension: {extension}. Valid extensions are: {VALID_EXTENSIONS}. {reminder}"
        )

    if img_type not in [bf_suffix, fl_suffix]:
        raise Exception(
            f"Invalid suffix for image type: {img_type}. Valid suffixes are: {bf_suffix} (brightfield) and {fl_suffix} (fluorescent). {reminder}"
        )

    return sample_name, img_type
