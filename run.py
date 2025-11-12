from __future__ import annotations

import argparse
import cv2
import os

from config import (
    DEFAULT_BRIGHTFIELD_SUFFIX,
    DEFAULT_FLUORESCENT_SUFFIX,
    INITIAL_BRIGHTNESS_THRESHOLDS,
)
from seeds import process_seed_image, process_colorimetric_image
from utils import (
    VALID_EXTENSIONS,
    CountMethod,
    Result,
    parse_filename,
    store_results,
)

DEFAULT_BRIGHTFIELD_THESHOLD = INITIAL_BRIGHTNESS_THRESHOLDS[DEFAULT_BRIGHTFIELD_SUFFIX]
DEFAULT_FLUORESCENT_THRESHOLD = INITIAL_BRIGHTNESS_THRESHOLDS[
    DEFAULT_FLUORESCENT_SUFFIX
]

from typing import Dict, Iterator, List, Tuple


def process_fluorescent_batch(
    sample_to_files: Dict[str, List[Dict[str, str]]],
    bf_thresh: int | None,
    fl_thresh: int | None,
    radial_thresh: float | None,
    batch_output_dir: str | None,
    bf_suffix: str | None = None,
    fl_suffix: str | None = None,
    radial_threshold_ratio: float | None = None,
    large_area_factor: float | None = None,
    plot: bool = True,
) -> Iterator[str | List[Result]]:
    """Process a batch of paired brightfield/fluorescent images.

    Parameters
    ----------
    sample_to_files:
        Mapping of sample name to a list of file descriptors. Each descriptor
        must contain ``file_path``, ``file_name`` and ``img_type``.
    bf_thresh:
        Initial threshold for the brightfield image or ``None`` for automatic
        thresholding.
    fl_thresh:
        Initial threshold for the fluorescent image or ``None`` for automatic
        thresholding.
    radial_thresh:
        Distance transform threshold used for seed separation. If ``None`` the
        value is computed automatically.
    batch_output_dir:
        Directory where intermediate images will be stored. ``None`` disables
        saving images.
    bf_suffix / fl_suffix:
        Filename suffixes identifying brightfield and fluorescent images.
    radial_threshold_ratio:
        Fraction of the median seed radius used when computing
        ``radial_thresh`` automatically.
    large_area_factor:
        Factor relative to median seed area used to discard very large regions.
    plot:
        If ``True`` show intermediate processing plots.

    Yields
    ------
    str or List[Result]
        Status messages during processing followed by the full list of results
        once the batch is finished.
    """
    bf_suffix = bf_suffix or DEFAULT_BRIGHTFIELD_SUFFIX
    fl_suffix = fl_suffix or DEFAULT_FLUORESCENT_SUFFIX

    results = []
    for i, sample_name in enumerate(sorted(sample_to_files.keys())):
        yield f"Processing sample {sample_name} ({i+1} of {len(sample_to_files.keys())}):"
        result = Result(sample_name)
        result.radial_threshold_ratio = radial_threshold_ratio
        for file_obj in sample_to_files[sample_name]:
            file_path = file_obj["file_path"]
            filename = file_obj["file_name"]
            img_type = file_obj["img_type"]

            image = cv2.imread(file_path)
            if img_type == bf_suffix:
                yield f"\t{bf_suffix} (brightfield) image: {filename}"
                img_type_name = DEFAULT_BRIGHTFIELD_SUFFIX
                process_seed_result = process_seed_image(
                    image=image,
                    img_type=img_type_name,
                    sample_name=sample_name,
                    initial_brightness_thresh=bf_thresh,
                    radial_threshold=radial_thresh,
                    radial_threshold_ratio=radial_threshold_ratio,
                    image_L=None,
                    large_area_factor=large_area_factor,
                    output_dir=batch_output_dir,
                    plot=plot,
                )
                result.total_seeds = process_seed_result.num_seeds
                result.bf_thresh = process_seed_result.brightness_threshold
                result.radial_threshold = process_seed_result.radial_threshold
            elif img_type == fl_suffix:
                yield f"\t{fl_suffix} (fluorescent) image: {filename}"
                img_type_name = DEFAULT_FLUORESCENT_SUFFIX
                process_seed_result = process_seed_image(
                    image=image,
                    img_type=img_type_name,
                    sample_name=sample_name,
                    initial_brightness_thresh=fl_thresh,
                    radial_threshold=radial_thresh,
                    image_L=None,
                    radial_threshold_ratio=radial_threshold_ratio,
                    large_area_factor=large_area_factor,
                    output_dir=batch_output_dir,
                    plot=plot,
                )
                result.marker_seeds = process_seed_result.num_seeds
                result.marker_thresh = process_seed_result.brightness_threshold
                result.radial_threshold = process_seed_result.radial_threshold
            else:
                yield f"\tUnknown image type for {filename}"

        if not result.total_seeds:
            yield f"\tCouldn't find {bf_suffix} (brightfield) image for {sample_name}. Remember that image should be named <prefix_id>_{bf_suffix}.<img_extension>. Example: img1_{bf_suffix}.tif"
        if not result.marker_seeds:
            yield f"\tCouldn't find {fl_suffix} (fluorescent) image for {sample_name}. Remember that image should be named <prefix_id>_{fl_suffix}.<img_extension>. Example: img1_{fl_suffix}.tif"

        results.append(result)

    yield results


def process_colorimetric_batch(
    sample_to_file: Dict[str, List[Dict[str, str]]],
    bf_thresh: int | None,
    radial_thresh: float | None,
    batch_output_dir: str | None,
    radial_threshold_ratio: float | None = None,
    large_area_factor: float | None = None,
    plot: bool = True,
) -> Iterator[str | List[Result]]:
    """Process a batch of single RGB images.

    Parameters
    ----------
    sample_to_file:
        Mapping of sample names to a list containing one file descriptor for the
        RGB image. Each descriptor must include ``file_path`` and ``file_name``.
    bf_thresh, fl_thresh:
        Optional fixed thresholds for counting all seeds and marker seeds.
    radial_thresh:
        Optional distance transform threshold. Computed automatically when
        ``None``.
    batch_output_dir:
        Directory where output images will be stored. ``None`` disables writing
        images.
    radial_threshold_ratio:
        Ratio used to compute ``radial_thresh`` from the median seed size when
        ``radial_thresh`` is ``None``.
    large_area_factor:
        Factor relative to median seed area used to remove large clumps.
    plot:
        If ``True`` display intermediate plots for each image.

    Yields
    ------
    str or List[Result]
        Informational messages followed by the final results list.
    """

    results = []
    for i, sample_name in enumerate(sorted(sample_to_file.keys())):
        yield f"Processing sample {sample_name} ({i+1} of {len(sample_to_file)}):"
        assert len(sample_to_file[sample_name]), "Sample should have only one image"
        file_path = sample_to_file[sample_name][0]["file_path"]
        all_seeds_process_result, colored_seeds_process_result = (
            process_colorimetric_image(
                image_path=file_path,
                sample_name=sample_name,
                bf_thresh=bf_thresh,
                radial_threshold=radial_thresh,
                radial_threshold_ratio=radial_threshold_ratio,
                output_dir=batch_output_dir,
                large_area_factor=large_area_factor,
                plot=plot,
            )
        )
        result = Result(sample_name)
        result.total_seeds = all_seeds_process_result.num_seeds
        result.bf_thresh = all_seeds_process_result.brightness_threshold
        result.marker_seeds = colored_seeds_process_result.num_seeds
        result.marker_thresh = colored_seeds_process_result.brightness_threshold
        result.radial_threshold = all_seeds_process_result.radial_threshold
        result.radial_threshold_ratio = radial_threshold_ratio
        results.append(result)

        if not result.total_seeds:
            yield f"\tDid not find any seeds for {sample_name}."

        if not result.marker_seeds:
            yield f"\tDid not find any marker seeds for {sample_name}. Make sure that the marker seeds are RED and that the non-marker seeds are YELLOW-ish. Other colors are not supported yet."

        if result.marker_seeds and result.total_seeds:
            yield f"\tSuccessfully processed {sample_name}"
        else:
            yield f"\tAdjust parameters to improve results for {sample_name}. See instructions for guidelines on how to ideally set them."

        yield f"\tResults for {sample_name}: {results[-1]}"

    yield results


def print_welcome_msg() -> None:
    print("Welcome to SeedSeg!")
    print(
        "For fluorescence mode, provide pairs of images: "
        f"{DEFAULT_BRIGHTFIELD_SUFFIX} (brightfield) and {DEFAULT_FLUORESCENT_SUFFIX} (fluorescent)."
    )
    print("For color mode, provide a single RGB image per sample.")
    print()


def collect_img_files(
    input_dir: str,
    bf_suffix: str,
    fl_suffix: str,
) -> tuple[Dict[str, List[Dict[str, str]]], List[str]]:
    """Gather paired image files from a directory.

    Parameters
    ----------
    input_dir:
        Directory containing the images to process.
    bf_suffix, fl_suffix:
        Expected suffixes identifying brightfield and fluorescent images.

    Returns
    -------
    tuple
        Mapping from sample names to their file descriptors and the list of all
        filenames discovered.
    """
    file_names = [
        f
        for f in os.listdir(input_dir)
        if os.path.isfile(os.path.join(input_dir, f))
        and os.path.splitext(f)[-1].lower() in VALID_EXTENSIONS
    ]

    sample_to_files = {}
    for filename in file_names:
        sample_name, img_type = parse_filename(filename, bf_suffix, fl_suffix)
        file_obj = {
            "file_path": os.path.join(input_dir, filename),
            "file_name": filename,
            "img_type": img_type,
        }
        if sample_name not in sample_to_files:
            sample_to_files[sample_name] = [file_obj]
        else:
            sample_to_files[sample_name].append(file_obj)

    return sample_to_files, file_names


def collect_single_img_files(
    input_dir: str,
) -> tuple[Dict[str, List[Dict[str, str]]], List[str]]:
    """Collect single RGB images from ``input_dir``.

    The file name (without extension) is used as the sample name.

    Returns a mapping from sample names to a list containing one file descriptor
    as well as the list of discovered filenames.
    """
    file_names = [
        f
        for f in os.listdir(input_dir)
        if os.path.isfile(os.path.join(input_dir, f))
        and os.path.splitext(f)[-1].lower() in VALID_EXTENSIONS
    ]

    sample_to_file = {}
    for filename in file_names:
        sample_name = os.path.splitext(filename)[0]
        file_obj = {
            "file_path": os.path.join(input_dir, filename),
            "file_name": filename,
        }
        sample_to_file[sample_name] = [file_obj]

    return sample_to_file, file_names


if __name__ == "__main__":
    help_message = "This script takes an image or directory of images and returns the number of seeds in the image(s)."
    parser = argparse.ArgumentParser(
        description=help_message, argument_default=argparse.SUPPRESS
    )
    parser.add_argument(
        "-d",
        "--dir",
        type=str,
        help="Path to the image directory. Required",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Path to the output directory. Required",
        required=True,
    )
    parser.add_argument(
        "-n",
        "--nostore",
        action="store_true",
        help="Do not store output images in output directory (but still store results .csv file)",
        default=False,
    )
    parser.add_argument(
        "-p", "--plot", action="store_true", help="Plot images", default=False
    )
    parser.add_argument(
        "-t",
        "--intensity_thresh",
        type=str,
        help='Intensity threshold to capture seeds. Format is <brightfield_thresh>,<fluorescent_thresh>. Example: "30,30". Default: None',
        default=None,
    )
    parser.add_argument(
        "-r",
        "--radial_thresh",
        type=float,
        help="Radial threshold to capture seeds. If not given, this value is set by taking the median area as a reference.",
        default=None,
    )
    parser.add_argument(
        "-s",
        "--img_type_suffix",
        type=str,
        help='Image type suffix. Format is <brightfield_suffix>,<fluorescent_suffix>. Example: BF,FL. Default: "%(default)s"',
        default=f"{DEFAULT_BRIGHTFIELD_SUFFIX},{DEFAULT_FLUORESCENT_SUFFIX}",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=[CountMethod.FLUORESCENCE.value, CountMethod.COLORIMETRIC.value],
        default=CountMethod.FLUORESCENCE.value,
        help="Counting mode to use.",
    )
    parser.add_argument(
        "--radial_threshold_ratio",
        type=float,
        default=0.4,
        help="Compute the radial threshold as a ratio of the median area of the seeds. Default: 0.4",
    )
    parser.add_argument(
        "--large_area_factor",
        type=float,
        default=None,
        help="Factor to determine the maximum allowed area for a seed (relative to median area). Used to filter out very large objects. Default is None, meaning that the operation won't be performed.",
    )

    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if args.intensity_thresh is not None:
        try:
            bf_thresh, fl_thresh = [int(x) for x in args.intensity_thresh.split(",")]
        except:
            raise Exception(
                "Invalid intensity threshold format. Format is <brightfield_thresh>,<fluorescent_thresh>. Example: 60,60"
            )
    else:
        bf_thresh, fl_thresh = None, None

    if args.mode != CountMethod.COLORIMETRIC.value:
        try:
            bf_suffix, fl_suffix = args.img_type_suffix.split(",")
        except Exception:
            raise Exception(
                "Invalid image type suffix format. Format is <brightfield_suffix>,<fluorescent_suffix>. Example: BF,FL"
            )
    else:
        bf_suffix, fl_suffix = None, None

    print_welcome_msg()

    if args.mode == CountMethod.FLUORESCENCE.value:
        sample_to_files, file_names = collect_img_files(args.dir, bf_suffix, fl_suffix)
    else:
        sample_to_files, file_names = collect_single_img_files(args.dir)
    print(
        f"Found {len(sample_to_files.keys())} unique samples in {len(file_names)} files"
    )

    # Determine whether to store intermediate images
    img_output_dir = None if args.nostore else args.output

    # Process images
    results = []
    if args.mode == CountMethod.FLUORESCENCE.value:
        iterator = process_fluorescent_batch(
            sample_to_files=sample_to_files,
            bf_thresh=bf_thresh,
            fl_thresh=fl_thresh,
            radial_thresh=args.radial_thresh,
            batch_output_dir=img_output_dir,
            bf_suffix=bf_suffix,
            fl_suffix=fl_suffix,
            radial_threshold_ratio=args.radial_threshold_ratio,
            large_area_factor=args.large_area_factor,
            plot=args.plot,
        )
    else:
        iterator = process_colorimetric_batch(
            sample_to_file=sample_to_files,
            bf_thresh=bf_thresh,
            radial_thresh=args.radial_thresh,
            batch_output_dir=img_output_dir,
            radial_threshold_ratio=args.radial_threshold_ratio,
            large_area_factor=args.large_area_factor,
            plot=args.plot,
        )

    for message in iterator:
        if isinstance(message, str):
            print(message)
        else:
            results = message

    # Results CSV is always stored in the output directory
    store_results(results, args.output)

    print("Thanks for your visit!")
