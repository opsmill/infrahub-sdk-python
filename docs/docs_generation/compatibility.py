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
# Auto-updated by update_compatibility.py.
VERSION_RANGES: list[VersionRange] = [
    VersionRange(infrahub="1.10.x", min_sdk="1.22.0", date="June 2026"),
    VersionRange(infrahub="1.9.x", min_sdk="1.20.0", date="April 2026"),
    VersionRange(infrahub="1.8.x", min_sdk="1.19.0", date="March 2026"),
    VersionRange(infrahub="1.7.x", min_sdk="1.18.1", date="January 2026"),
    VersionRange(infrahub="1.6.x", min_sdk="1.16.0", date="December 2025"),
    VersionRange(infrahub="1.5.x", min_sdk="1.15.0", date="November 2025"),
    VersionRange(infrahub="1.4.x", min_sdk="1.13.5", date="August 2025"),
    VersionRange(infrahub="1.3.x", min_sdk="1.13.0", date="June 2025"),
    VersionRange(infrahub="1.2.x", min_sdk="1.8.0", date="March 2025"),
    VersionRange(infrahub="1.1.x", min_sdk="1.3.0", date="December 2024"),
    VersionRange(infrahub="1.0.x", min_sdk="1.0.0", date="October 2024"),
    VersionRange(infrahub="0.16.x", min_sdk="0.13.1", date="September 2024"),
]

# Detailed mapping of every Infrahub release to its pinned SDK version.
# Auto-updated by update_compatibility.py.
RELEASE_MAPPINGS: list[ReleaseMapping] = [
    ReleaseMapping(infrahub="1.10.6", sdk="1.22.2", date="2026-07-28"),
    ReleaseMapping(infrahub="1.10.5", sdk="1.22.1", date="2026-07-15"),
    ReleaseMapping(infrahub="1.10.4", sdk="1.22.1", date="2026-07-13"),
    ReleaseMapping(infrahub="1.10.3", sdk="1.22.1", date="2026-07-08"),
    ReleaseMapping(infrahub="1.10.2", sdk="1.22.0", date="2026-07-03"),
    ReleaseMapping(infrahub="1.10.1", sdk="1.22.0", date="2026-07-01"),
    ReleaseMapping(infrahub="1.10.0", sdk="1.22.0", date="2026-06-23"),
    ReleaseMapping(infrahub="1.9.10", sdk="1.20.1", date="2026-07-07"),
    ReleaseMapping(infrahub="1.9.9", sdk="1.20.1", date="2026-06-23"),
    ReleaseMapping(infrahub="1.9.8", sdk="1.20.1", date="2026-06-09"),
    ReleaseMapping(infrahub="1.9.7", sdk="1.20.1", date="2026-06-03"),
    ReleaseMapping(infrahub="1.9.6", sdk="1.20.1", date="2026-05-20"),
    ReleaseMapping(infrahub="1.9.5", sdk="1.20.0", date="2026-05-18"),
    ReleaseMapping(infrahub="1.9.4", sdk="1.20.0", date="2026-05-13"),
    ReleaseMapping(infrahub="1.9.3", sdk="1.20.0", date="2026-05-05"),
    ReleaseMapping(infrahub="1.9.2", sdk="1.20.0", date="2026-04-30"),
    ReleaseMapping(infrahub="1.9.1", sdk="1.20.0", date="2026-04-29"),
    ReleaseMapping(infrahub="1.9.0", sdk="1.20.0", date="2026-04-24"),
    ReleaseMapping(infrahub="1.8.7", sdk="1.19.0", date="2026-06-04"),
    ReleaseMapping(infrahub="1.8.6", sdk="1.19.0", date="2026-04-21"),
    ReleaseMapping(infrahub="1.8.5", sdk="1.19.0", date="2026-04-17"),
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
    ReleaseMapping(infrahub="1.4.13", sdk="1.13.5", date="2025-11-06"),
    ReleaseMapping(infrahub="1.4.12", sdk="1.13.5", date="2025-10-23"),
    ReleaseMapping(infrahub="1.4.11", sdk="1.13.5", date="2025-10-17"),
    ReleaseMapping(infrahub="1.4.10", sdk="1.13.5", date="2025-10-01"),
    ReleaseMapping(infrahub="1.4.9", sdk="1.13.5", date="2025-09-26"),
    ReleaseMapping(infrahub="1.4.8", sdk="1.13.5", date="2025-09-23"),
    ReleaseMapping(infrahub="1.4.7", sdk="1.13.5", date="2025-09-16"),
    ReleaseMapping(infrahub="1.4.6", sdk="1.13.5", date="2025-09-10"),
    ReleaseMapping(infrahub="1.4.5", sdk="1.14.0", date="2025-09-08"),
    ReleaseMapping(infrahub="1.4.4", sdk="1.13.5", date="2025-09-03"),
    ReleaseMapping(infrahub="1.4.3", sdk="1.13.5", date="2025-08-29"),
    ReleaseMapping(infrahub="1.4.2", sdk="1.13.5", date="2025-08-28"),
    ReleaseMapping(infrahub="1.4.1", sdk="1.13.5", date="2025-08-27"),
    ReleaseMapping(infrahub="1.4.0", sdk="1.13.5", date="2025-08-26"),
    ReleaseMapping(infrahub="1.3.9", sdk="1.13.5", date="2025-09-08"),
    ReleaseMapping(infrahub="1.3.8", sdk="1.13.5", date="2025-08-26"),
    ReleaseMapping(infrahub="1.3.7", sdk="1.13.5", date="2025-08-14"),
    ReleaseMapping(infrahub="1.3.6", sdk="1.13.5", date="2025-08-11"),
    ReleaseMapping(infrahub="1.3.5", sdk="1.13.5", date="2025-08-05"),
    ReleaseMapping(infrahub="1.3.4", sdk="1.13.5", date="2025-07-24"),
    ReleaseMapping(infrahub="1.3.3", sdk="1.13.3", date="2025-07-15"),
    ReleaseMapping(infrahub="1.3.2", sdk="1.13.3", date="2025-06-30"),
    ReleaseMapping(infrahub="1.3.1", sdk="1.13.2", date="2025-06-27"),
    ReleaseMapping(infrahub="1.3.0", sdk="1.13.0", date="2025-06-12"),
    ReleaseMapping(infrahub="1.2.12", sdk="1.12.1", date="2025-06-03"),
    ReleaseMapping(infrahub="1.2.11", sdk="1.12.1", date="2025-05-23"),
    ReleaseMapping(infrahub="1.2.10", sdk="1.12.1", date="2025-05-14"),
    ReleaseMapping(infrahub="1.2.9", sdk="1.12.0", date="2025-05-07"),
    ReleaseMapping(infrahub="1.2.8", sdk="1.12.0", date="2025-05-01"),
    ReleaseMapping(infrahub="1.2.7", sdk="1.11.1", date="2025-04-28"),
    ReleaseMapping(infrahub="1.2.6", sdk="1.10.2", date="2025-04-18"),
    ReleaseMapping(infrahub="1.2.5", sdk="1.10.2", date="2025-04-12"),
    ReleaseMapping(infrahub="1.2.4", sdk="1.10.1", date="2025-04-04"),
    ReleaseMapping(infrahub="1.2.3", sdk="1.10.0", date="2025-04-01"),
    ReleaseMapping(infrahub="1.2.2", sdk="1.9.2", date="2025-03-28"),
    ReleaseMapping(infrahub="1.2.1", sdk="1.9.1", date="2025-03-26"),
    ReleaseMapping(infrahub="1.2.0", sdk="1.8.0", date="2025-03-21"),
    ReleaseMapping(infrahub="1.1.10", sdk="1.7.2", date="2025-04-01"),
    ReleaseMapping(infrahub="1.1.9", sdk="1.7.2", date="2025-03-17"),
    ReleaseMapping(infrahub="1.1.8", sdk="1.7.2", date="2025-03-08"),
    ReleaseMapping(infrahub="1.1.7", sdk="1.7.0", date="2025-02-18"),
    ReleaseMapping(infrahub="1.1.6", sdk="1.7.1", date="2025-01-31"),
    ReleaseMapping(infrahub="1.1.5", sdk="1.7.0", date="2025-01-24"),
    ReleaseMapping(infrahub="1.1.4", sdk="1.6.1", date="2025-01-17"),
    ReleaseMapping(infrahub="1.1.3", sdk="1.6.0", date="2025-01-16"),
    ReleaseMapping(infrahub="1.1.2", sdk="1.5.0", date="2025-01-09"),
    ReleaseMapping(infrahub="1.1.1", sdk="1.4.0", date="2025-01-06"),
    ReleaseMapping(infrahub="1.1.0", sdk="1.3.0", date="2024-12-30"),
    ReleaseMapping(infrahub="1.0.10", sdk="1.1.0", date="2024-12-20"),
    ReleaseMapping(infrahub="1.0.9", sdk="1.1.0", date="2024-12-13"),
    ReleaseMapping(infrahub="1.0.8", sdk="1.1.0", date="2024-12-03"),
    ReleaseMapping(infrahub="1.0.7", sdk="1.0.1", date="2024-11-20"),
    ReleaseMapping(infrahub="1.0.6", sdk="1.0.1", date="2024-11-18"),
    ReleaseMapping(infrahub="1.0.5", sdk="1.0.1", date="2024-11-15"),
    ReleaseMapping(infrahub="1.0.4", sdk="1.0.1", date="2024-11-13"),
    ReleaseMapping(infrahub="1.0.3", sdk="1.0.0", date="2024-11-08"),
    ReleaseMapping(infrahub="1.0.2", sdk="1.0.0", date="2024-11-06"),
    ReleaseMapping(infrahub="1.0.1", sdk="1.0.0", date="2024-10-31"),
    ReleaseMapping(infrahub="0.16.4", sdk="0.14.0", date="2024-10-17"),
    ReleaseMapping(infrahub="0.16.3", sdk="0.14.0", date="2024-10-10"),
    ReleaseMapping(infrahub="0.16.2", sdk="0.13.1", date="2024-10-01"),
    ReleaseMapping(infrahub="0.16.1", sdk="0.13.1", date="2024-09-25"),
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
