from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


def test_help_message(pytester: pytest.Pytester) -> None:
    """Make sure that the plugin is loaded by capturing an option it adds in the help message."""
    result = pytester.runpytest("--help")
    result.stdout.fnmatch_lines(["*Infrahub configuration file for the repository*"])


def test_without_config(pytester: pytest.Pytester) -> None:
    """Make sure 0 tests run when test file is not found."""
    result = pytester.runpytest()
    result.assert_outcomes()


def test_emptyconfig(pytester: pytest.Pytester) -> None:
    """Make sure that the plugin load the test file properly."""
    pytester.makefile(
        ".yml",
        test_empty="""
        ---
        version: "1.0"
        infrahub_tests: []
    """,
    )

    result = pytester.runpytest()
    result.assert_outcomes()


def test_jinja2_transform_config_missing_directory(pytester: pytest.Pytester) -> None:
    """Make sure tests raise errors if directories are not found."""
    pytester.makefile(
        ".yml",
        test_jinja2_transform="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "Jinja2Transform"
            resource_name: "bgp_config"
            tests:
              - name: "base"
                expect: PASS
                spec:
                  kind: "jinja2-transform-unit-render"
                  directory: bgp_config/base
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas:
          - schemas/demo_edge_fabric.yml

        jinja2_transforms:
          - name: bgp_config
            description: "Template for BGP config base"
            query: "bgp_sessions"
            template_path: "templates/bgp_config.j2"

    """,
    )

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(errors=1)


def test_jinja2_transform_config_missing_input(pytester: pytest.Pytester) -> None:
    """Make sure tests raise errors if no inputs are provided."""
    pytester.makefile(
        ".yml",
        test_jinja2_transform="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "Jinja2Transform"
            resource_name: "bgp_config"
            tests:
              - name: "base"
                expect: PASS
                spec:
                  kind: "jinja2-transform-unit-render"
                  directory: bgp_config/base
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas:
          - schemas/demo_edge_fabric.yml

        jinja2_transforms:
          - name: bgp_config
            description: "Template for BGP config base"
            query: "bgp_sessions"
            template_path: "templates/bgp_config.j2"

    """,
    )

    pytester.mkdir("bgp_config")
    pytester.mkdir("bgp_config/base")

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(errors=1)


def test_jinja2_transform_no_expected_output(pytester: pytest.Pytester) -> None:
    """Make sure tests succeed if no expect outputs are provided."""
    pytester.makefile(
        ".yml",
        test_jinja2_transform="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "Jinja2Transform"
            resource_name: "bgp_config"
            tests:
              - name: "base"
                expect: PASS
                spec:
                  kind: "jinja2-transform-unit-render"
                  directory: bgp_config/base
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas:
          - schemas/demo_edge_fabric.yml

        jinja2_transforms:
          - name: bgp_config
            description: "Template for BGP config base"
            query: "bgp_sessions"
            template_path: "templates/bgp_config.j2"

    """,
    )

    pytester.mkdir("bgp_config")
    test_dir = pytester.mkdir("bgp_config/base")
    test_input = pytester.makefile(".json", input='{"data": {}}')
    pytester.run("mv", test_input, test_dir)

    template_dir = pytester.mkdir("templates")
    template = pytester.makefile(
        ".j2",
        bgp_config="""
    protocols {
        bgp {
            log-up-down;
            bgp-error-tolerance;
        }
    }
    """,
    )
    pytester.run("mv", template, template_dir)

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(passed=1)


def test_jinja2_transform_unexpected_output(pytester: pytest.Pytester) -> None:
    """Make sure tests fail if the expected and computed outputs don't match."""
    pytester.makefile(
        ".yml",
        test_jinja2_transform="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "Jinja2Transform"
            resource_name: "bgp_config"
            tests:
              - name: "base"
                expect: PASS
                spec:
                  kind: "jinja2-transform-unit-render"
                  directory: bgp_config/base
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas:
          - schemas/demo_edge_fabric.yml

        jinja2_transforms:
          - name: bgp_config
            description: "Template for BGP config base"
            query: "bgp_sessions"
            template_path: "templates/bgp_config.j2"

    """,
    )

    pytester.mkdir("bgp_config")
    test_dir = pytester.mkdir("bgp_config/base")
    test_input = pytester.makefile(".json", input='{"data": {}}')
    test_output = pytester.makefile(
        ".txt",
        output="""
    protocols {
        bgp {
            group ipv4-ibgp {
                peer-as 64545;
            }
            log-up-down;
            bgp-error-tolerance;
        }
    }
    """,
    )
    pytester.run("mv", test_input, test_dir)
    pytester.run("mv", test_output, test_dir)

    template_dir = pytester.mkdir("templates")
    template = pytester.makefile(
        ".j2",
        bgp_config="""
    protocols {
        bgp {
            log-up-down;
            bgp-error-tolerance;
        }
    }
    """,
    )
    pytester.run("mv", template, template_dir)

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(failed=1)


def test_python_transform(pytester: pytest.Pytester) -> None:
    pytester.makefile(
        ".yml",
        test_python_transform="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "PythonTransform"
            resource_name: "device_config"
            tests:
              - name: "base_config"
                expect: PASS
                spec:
                  kind: "python-transform-unit-process"
                  directory: device_config/base_config
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas:
          - schemas/dcim.yml

        python_transforms:
          - name: device_config
            class_name: "DeviceConfig"
            file_path: "transforms/device_config.py"
    """,
    )
    test_input = pytester.makefile(
        ".json", input='{"data": { "InfraDevice": { "edges": [ { "node": { "name": {"value": "atl1-edge1"} } } ] } } }'
    )
    test_output = pytester.makefile(".json", output='{"hostname": "atl1-edge1"}')
    test_template = pytester.makefile(
        ".py",
        device_config="""
        from infrahub_sdk.transforms import InfrahubTransform

        class DeviceConfig(InfrahubTransform):
            query = "device_config"
            async def transform(self, data):
                return {"hostname": data["InfraDevice"]["edges"][0]["node"]["name"]["value"]}
    """,
    )

    pytester.mkdir("device_config")
    test_dir = pytester.mkdir("device_config/base_config")
    pytester.run("mv", test_input, test_dir)
    pytester.run("mv", test_output, test_dir)

    transform_dir = pytester.mkdir("transforms")
    pytester.run("mv", test_template, transform_dir)

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(passed=1)


def test_graphql_query_smoke(pytester: pytest.Pytester) -> None:
    """Smoke item should pass when the query file exists and parses successfully."""
    pytester.makefile(
        ".yml",
        test_graphql_query="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "GraphQLQuery"
            resource_name: "device_query"
            tests:
              - name: "smoke"
                expect: PASS
                spec:
                  kind: "graphql-query-smoke"
                  path: "queries/device.gql"
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas: []
    """,
    )
    queries_dir = pytester.mkdir("queries")
    query_file = pytester.makefile(
        ".gql",
        device="""
        query DeviceQuery {
            InfraDevice {
                edges {
                    node {
                        name { value }
                    }
                }
            }
        }
        """,
    )
    pytester.run("mv", query_file, queries_dir)

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(passed=1)


def test_graphql_query_smoke_invalid(pytester: pytest.Pytester) -> None:
    """Smoke item should fail when the query file contains invalid GraphQL."""
    pytester.makefile(
        ".yml",
        test_graphql_query="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "GraphQLQuery"
            resource_name: "device_query"
            tests:
              - name: "smoke"
                expect: PASS
                spec:
                  kind: "graphql-query-smoke"
                  path: "queries/broken.gql"
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas: []
    """,
    )
    queries_dir = pytester.mkdir("queries")
    query_file = pytester.makefile(
        ".gql",
        broken="this is not a valid graphql query {",
    )
    pytester.run("mv", query_file, queries_dir)

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(failed=1)


def test_jinja2_transform_smoke(pytester: pytest.Pytester) -> None:
    """Smoke item should pass when the template parses successfully."""
    pytester.makefile(
        ".yml",
        test_jinja2_transform="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "Jinja2Transform"
            resource_name: "bgp_config"
            tests:
              - name: "smoke"
                expect: PASS
                spec:
                  kind: "jinja2-transform-smoke"
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas: []

        jinja2_transforms:
          - name: bgp_config
            description: "Template for BGP config base"
            query: "bgp_sessions"
            template_path: "templates/bgp_config.j2"
    """,
    )
    template_dir = pytester.mkdir("templates")
    template = pytester.makefile(
        ".j2",
        bgp_config="""
    protocols {
        bgp {
            log-up-down;
            bgp-error-tolerance;
        }
    }
    """,
    )
    pytester.run("mv", template, template_dir)

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(passed=1)


@pytest.mark.httpx_mock(can_send_already_matched_responses=True)
def test_graphql_query_integration(pytester: pytest.Pytester, httpx_mock: HTTPXMock) -> None:
    """Integration item should pass when the mocked GraphQL response matches the expected output."""
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/api/query/device_query?branch=main&update_group=false&",
        json={"data": {"InfraDevice": {"edges": [{"node": {"name": {"value": "atl1-edge1"}}}]}}},
        is_reusable=True,
    )

    pytester.makefile(
        ".yml",
        test_graphql_query="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "GraphQLQuery"
            resource_name: "device_query"
            tests:
              - name: "integration"
                expect: PASS
                spec:
                  kind: "graphql-query-integration"
                  query: "device_query"
                  variables: {}
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas: []
    """,
    )

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(passed=1)


@pytest.mark.httpx_mock(can_send_already_matched_responses=True)
def test_jinja2_transform_integration(pytester: pytest.Pytester, httpx_mock: HTTPXMock) -> None:
    """Integration item should render the template using data from a mocked GraphQL response."""
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/api/query/bgp_sessions?branch=main&update_group=false&",
        json={"data": {"BgpSession": {"edges": []}}},
        is_reusable=True,
    )

    pytester.makefile(
        ".yml",
        test_jinja2_transform="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "Jinja2Transform"
            resource_name: "bgp_config"
            tests:
              - name: "integration"
                expect: PASS
                spec:
                  kind: "jinja2-transform-integration"
                  variables: {}
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas: []

        jinja2_transforms:
          - name: bgp_config
            description: "Template for BGP config base"
            query: "bgp_sessions"
            template_path: "templates/bgp_config.j2"
    """,
    )
    template_dir = pytester.mkdir("templates")
    template = pytester.makefile(
        ".j2",
        bgp_config="""
    protocols {
        bgp {
            log-up-down;
            bgp-error-tolerance;
        }
    }
    """,
    )
    pytester.run("mv", template, template_dir)

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(passed=1)


@pytest.mark.httpx_mock(can_send_already_matched_responses=True)
def test_python_transform_integration(pytester: pytest.Pytester, httpx_mock: HTTPXMock) -> None:
    """Integration item should run the transform using data from a mocked GraphQL response."""
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/api/query/device_config?branch=main&update_group=false&",
        json={"data": {"InfraDevice": {"edges": [{"node": {"name": {"value": "atl1-edge1"}}}]}}},
        is_reusable=True,
    )

    pytester.makefile(
        ".yml",
        test_python_transform="""
        ---
        version: "1.0"
        infrahub_tests:
          - resource: "PythonTransform"
            resource_name: "device_config"
            tests:
              - name: "integration"
                expect: PASS
                spec:
                  kind: "python-transform-integration"
                  variables: {}
    """,
    )
    pytester.makefile(
        ".yml",
        infrahub_config="""
        ---
        schemas: []

        python_transforms:
          - name: device_config
            class_name: "DeviceConfig"
            file_path: "transforms/device_config.py"
    """,
    )
    test_template = pytester.makefile(
        ".py",
        device_config="""
        from infrahub_sdk.transforms import InfrahubTransform

        class DeviceConfig(InfrahubTransform):
            query = "device_config"
            async def transform(self, data):
                return {"hostname": data["InfraDevice"]["edges"][0]["node"]["name"]["value"]}
    """,
    )
    transform_dir = pytester.mkdir("transforms")
    pytester.run("mv", test_template, transform_dir)

    result = pytester.runpytest("--infrahub-repo-config=infrahub_config.yml")
    result.assert_outcomes(passed=1)
