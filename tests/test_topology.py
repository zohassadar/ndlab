import logging
import pathlib

import pytest
import yaml
import ndlab.labmaker as labmaker

logger = logging.getLogger(__name__)

TOPOLOGIES_DIRECTORY = pathlib.Path(__file__).parent / "topologies"
HL_SUFFIX = "-hl.yml"
LL_SUFFIX = "-ll.yml"


def get_hl_and_ll_topologies():
    results = []

    logger.info(f"Searching for topologies in {TOPOLOGIES_DIRECTORY}")
    for high_level_path in TOPOLOGIES_DIRECTORY.glob(f"*{HL_SUFFIX}"):
        logger.info(f"Opening {high_level_path}")
        high_level = yaml.safe_load(open(high_level_path))
        low_level_file = high_level_path.name.replace(HL_SUFFIX, LL_SUFFIX)
        low_level_path = TOPOLOGIES_DIRECTORY / low_level_file
        if not low_level_path.exists():
            raise RuntimeError(f"Unable to open {low_level_file}")
        low_level = yaml.safe_load(open(low_level_path))
        logger.info(f"Opening {low_level_path}")

        results.append(
            pytest.param(
                high_level,
                low_level,
                id=f"{high_level_path.name}->{low_level_path.name}",
            ),
        )
    return results


@pytest.mark.parametrize(
    "high_level,low_level",
    get_hl_and_ll_topologies(),
)
def test_conversion(high_level: dict, low_level: dict):
    assert labmaker.Topology(high_level).low_level == low_level
