"""Compatibility data between the Infrahub Python SDK and Infrahub server.

This module provides structured data for auto-generating the compatibility
matrix documentation page. Update the lists below when new releases are made.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReleaseMapping:
    """Maps an Infrahub server release to its pinned SDK version.

    Args:
        infrahub: Infrahub server version (e.g. "1.8.4").
        sdk: SDK version pinned to this release (e.g. "1.19.0").
        date: Infrahub release date in YYYY-MM-DD format.
    """

    infrahub: str
    sdk: str
    date: str


@dataclass
class VersionRange:
    """Maps an Infrahub minor version series to its minimum required SDK version.

    Args:
        infrahub: Infrahub minor version pattern (e.g. "1.8.x").
        min_sdk: Minimum required SDK version (e.g. "1.19.0").
        date: Approximate release month (e.g. "March 2026").
    """

    infrahub: str
    min_sdk: str
    date: str


@dataclass
class PythonSupport:
    """Maps an SDK version range to supported Python versions.

    Args:
        sdk_range: SDK version range description (e.g. ">= 1.17.0").
        python_versions: Comma-separated Python versions (e.g. "3.10, 3.11, 3.12, 3.13, 3.14").
    """

    sdk_range: str
    python_versions: str


@dataclass
class FeatureRequirement:
    """Documents a feature that requires specific minimum versions.

    Args:
        feature: Feature name or description.
        min_sdk: Minimum SDK version required.
        min_infrahub: Minimum Infrahub version required.
    """

    feature: str
    min_sdk: str
    min_infrahub: str


# Mapping of Infrahub minor version series to minimum SDK versions.
# Update this list when a new Infrahub minor version is released.
VERSION_RANGES: list[VersionRange] = [
    VersionRange(infrahub="1.8.x", min_sdk="1.19.0", date="March 2026"),
    VersionRange(infrahub="1.7.x", min_sdk="1.18.0", date="January 2026"),
    VersionRange(infrahub="1.6.x", min_sdk="1.16.0", date="December 2025"),
    VersionRange(infrahub="1.5.x", min_sdk="1.15.0", date="November 2025"),
    VersionRange(infrahub="1.4.x", min_sdk="1.13.5", date="August 2025"),
    VersionRange(infrahub="1.3.x", min_sdk="1.13.0", date="June 2025"),
]

# Detailed mapping of every Infrahub release to its pinned SDK version.
# Update this list when a new Infrahub patch release is made.
RELEASE_MAPPINGS: list[ReleaseMapping] = [
    ReleaseMapping(infrahub="1.8.4", sdk="1.19.0", date="2026-04-02"),
    ReleaseMapping(infrahub="1.8.3", sdk="1.19.0", date="2026-03-31"),
    ReleaseMapping(infrahub="1.8.2", sdk="1.19.0", date="2026-03-25"),
    ReleaseMapping(infrahub="1.8.1", sdk="1.19.0", date="2026-03-19"),
    ReleaseMapping(infrahub="1.8.0", sdk="1.19.0", date="2026-03-16"),
    ReleaseMapping(infrahub="1.7.7", sdk="1.18.1", date="2026-03-12"),
    ReleaseMapping(infrahub="1.7.6", sdk="1.18.1", date="2026-02-25"),
    ReleaseMapping(infrahub="1.7.5", sdk="1.18.1", date="2026-02-24"),
    ReleaseMapping(infrahub="1.7.4", sdk="1.18.1", date="2026-02-03"),
    ReleaseMapping(infrahub="1.7.3", sdk="1.18.1", date="2026-01-28"),
    ReleaseMapping(infrahub="1.7.2", sdk="1.18.1", date="2026-01-27"),
    ReleaseMapping(infrahub="1.7.1", sdk="1.18.1", date="2026-01-12"),
    ReleaseMapping(infrahub="1.7.0", sdk="1.18.1", date="2026-01-09"),
    ReleaseMapping(infrahub="1.6.3", sdk="1.17.0", date="2026-01-07"),
    ReleaseMapping(infrahub="1.6.2", sdk="1.17.0", date="2025-12-22"),
    ReleaseMapping(infrahub="1.6.1", sdk="1.17.0", date="2025-12-11"),
    ReleaseMapping(infrahub="1.6.0", sdk="1.16.0", date="2025-12-01"),
    ReleaseMapping(infrahub="1.5.5", sdk="1.15.1", date="2025-12-22"),
    ReleaseMapping(infrahub="1.5.4", sdk="1.15.1", date="2025-12-16"),
    ReleaseMapping(infrahub="1.5.3", sdk="1.15.1", date="2025-11-24"),
    ReleaseMapping(infrahub="1.5.2", sdk="1.15.1", date="2025-11-18"),
    ReleaseMapping(infrahub="1.5.1", sdk="1.15.1", date="2025-11-13"),
    ReleaseMapping(infrahub="1.5.0", sdk="1.15.0", date="2025-11-10"),
    ReleaseMapping(infrahub="1.4.1", sdk="1.13.5", date="2025-08-27"),
    ReleaseMapping(infrahub="1.4.0", sdk="1.13.5", date="2025-08-26"),
    ReleaseMapping(infrahub="1.3.3", sdk="1.13.3", date="2025-07-15"),
    ReleaseMapping(infrahub="1.3.2", sdk="1.13.3", date="2025-06-30"),
    ReleaseMapping(infrahub="1.3.1", sdk="1.13.2", date="2025-06-27"),
    ReleaseMapping(infrahub="1.3.0", sdk="1.13.0", date="2025-06-12"),
]

# Python version support by SDK version range.
PYTHON_SUPPORT: list[PythonSupport] = [
    PythonSupport(sdk_range=">= 1.17.0", python_versions="3.10, 3.11, 3.12, 3.13, 3.14"),
    PythonSupport(sdk_range="1.16.0", python_versions="3.10, 3.11, 3.12, 3.13"),
    PythonSupport(sdk_range="1.13.0 - 1.15.x", python_versions="3.9, 3.10, 3.11, 3.12, 3.13"),
]

# Features that require specific minimum versions of both SDK and Infrahub.
FEATURE_REQUIREMENTS: list[FeatureRequirement] = [
    FeatureRequirement(feature="infrahubctl branch report", min_sdk="1.19.0", min_infrahub="1.7"),
    FeatureRequirement(feature="FileObject support", min_sdk="1.19.0", min_infrahub="1.8"),
    FeatureRequirement(feature="NumberPool support", min_sdk="1.13.0", min_infrahub="1.3"),
]
