"""
Architectural Compliance Tests for MED13 Resource Library.

These tests validate that the codebase adheres to architectural standards
defined in:
- docs/EngineeringArchitecture.md
- docs/type_examples.md
- docs/frontend/EngenieeringArchitectureNext.md
- AGENTS.md

The tests check for:
1. Type safety violations (Any, cast usage)
2. Clean Architecture layer violations
3. Single Responsibility Principle violations
4. Monolithic code patterns
5. Import dependency violations
"""

import logging
import subprocess
import sys
from pathlib import Path

import pytest

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

logger = logging.getLogger(__name__)


@pytest.mark.architecture
class TestArchitecturalCompliance:
    """Test suite for architectural compliance validation."""

    def test_no_any_types_in_codebase(self) -> None:
        """
        Verify that no 'Any' types are used in the codebase.

        Per AGENTS.md: "NEVER USE `Any` - this is a strict requirement"
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for Any usage violations
        output = result.stdout + result.stderr
        any_violations = [
            line
            for line in output.splitlines()
            if "any_usage" in line.lower() and "error" in line.lower()
        ]

        if any_violations:
            violation_details = "\n".join(any_violations)
            pytest.fail(
                f"Found 'Any' type usage violations:\n{violation_details}\n\n"
                "Per AGENTS.md, 'Any' types are strictly forbidden. "
                "Use proper types from src/type_definitions/ instead.",
            )

    def test_no_cast_usage_in_codebase(self) -> None:
        """
        Verify that no 'cast' is used in the codebase.

        Per AGENTS.md: "we should not use ANY or cast"
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for cast usage violations
        output = result.stdout + result.stderr
        cast_violations = [
            line
            for line in output.splitlines()
            if "cast_usage" in line.lower() and "error" in line.lower()
        ]

        if cast_violations:
            violation_details = "\n".join(cast_violations)
            pytest.fail(
                f"Found 'cast' usage violations:\n{violation_details}\n\n"
                "Per AGENTS.md, 'cast' usage is strictly forbidden. "
                "Use proper type guards or fix the underlying type issue.",
            )

    def test_clean_architecture_layer_separation(self) -> None:
        """
        Verify Clean Architecture layer separation.

        Per EngineeringArchitecture.md:
        - Domain layer should not import from infrastructure
        - Application layer should not import from routes
        - Infrastructure should not import from routes
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for layer violation errors
        output = result.stdout + result.stderr
        layer_violations = [
            line
            for line in output.splitlines()
            if "layer_violation" in line.lower() and "error" in line.lower()
        ]

        if layer_violations:
            violation_details = "\n".join(layer_violations)
            pytest.fail(
                f"Found Clean Architecture layer violations:\n{violation_details}\n\n"
                "Per EngineeringArchitecture.md, layers must respect dependency "
                "inversion principle. Domain should not depend on infrastructure.",
            )

    def test_single_responsibility_principle(self) -> None:
        """
        Verify Single Responsibility Principle compliance.

        Checks for:
        - Files that are too large (>1000 lines)
        - Functions with high complexity
        - Classes with too many methods
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for SRP violations (warnings are acceptable, errors are not)
        output = result.stdout + result.stderr
        srp_errors = [
            line
            for line in output.splitlines()
            if (
                ("file_size" in line.lower() or "complexity" in line.lower())
                and "error" in line.lower()
            )
        ]

        if srp_errors:
            violation_details = "\n".join(srp_errors)
            pytest.fail(
                f"Found Single Responsibility Principle violations:\n{violation_details}\n\n"
                "Files should be focused and not exceed size/complexity thresholds.",
            )

    def test_architectural_validation_script_runs(self) -> None:
        """
        Verify that the architectural validation script runs successfully.

        This is a meta-test to ensure the validation infrastructure works.
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"

        assert (
            validator_script.exists()
        ), f"Architectural validation script not found at {validator_script}"

        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,  # Should complete quickly
        )

        # Script should run without crashing
        assert result.returncode in (0, 1), (
            f"Validation script crashed with return code {result.returncode}\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    def test_graph_service_boundary_validation(self) -> None:
        """
        Verify new code does not bypass the standalone graph-service boundary.

        Direct imports of graph internals are only allowed inside the graph
        service and a shrinking legacy allowlist during extraction.
        """
        validator_script = (
            PROJECT_ROOT / "scripts" / "validate_graph_service_boundary.py"
        )

        assert (
            validator_script.exists()
        ), f"Graph boundary validation script not found at {validator_script}"

        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            "Found graph boundary violations:\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    def test_no_monolithic_files(self) -> None:
        """
        Verify that no files exceed the maximum size threshold.

        Per Single Responsibility Principle, files should be focused and manageable.
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for files exceeding maximum size (errors, not warnings)
        output = result.stdout + result.stderr
        oversized_files = [
            line
            for line in output.splitlines()
            if "file_size" in line.lower()
            and "error" in line.lower()
            and "exceeds maximum size" in line.lower()
        ]

        if oversized_files:
            violation_details = "\n".join(oversized_files)
            pytest.fail(
                f"Found files exceeding maximum size threshold:\n{violation_details}\n\n"
                "Large files may violate Single Responsibility Principle. "
                "Consider splitting into smaller, focused modules.",
            )

    def test_srp_import_count(self) -> None:
        """
        Verify files don't have excessive imports (SRP violation).

        Per Single Responsibility Principle, files with many imports
        may be handling multiple responsibilities.
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for import count violations (errors, not warnings)
        output = result.stdout + result.stderr
        import_violations = [
            line
            for line in output.splitlines()
            if "import_count" in line.lower()
            and "error" in line.lower()
            and "too many imports" in line.lower()
        ]

        if import_violations:
            violation_details = "\n".join(import_violations)
            pytest.fail(
                f"Found files with excessive imports:\n{violation_details}\n\n"
                "Files with many imports may violate Single Responsibility Principle. "
                "Consider splitting into smaller, focused modules.",
            )

    def test_srp_function_parameters(self) -> None:
        """
        Verify functions don't have excessive parameters (SRP violation).

        Per Single Responsibility Principle, functions with many parameters
        often indicate the function is doing too much.
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for parameter count violations
        output = result.stdout + result.stderr
        param_violations = [
            line
            for line in output.splitlines()
            if "parameter_count" in line.lower()
            and "too many parameters" in line.lower()
        ]

        if param_violations:
            violation_details = "\n".join(param_violations)
            pytest.fail(
                f"Found functions with excessive parameters:\n{violation_details}\n\n"
                "Functions with many parameters may violate Single Responsibility Principle. "
                "Consider using a parameter object or splitting responsibilities.",
            )

    def test_json_type_usage_compliance(self) -> None:
        """
        Verify that code uses JSONObject/JSONValue instead of dict[str, Any].

        Per docs/type_examples.md and AGENTS.md, dict[str, Any] should be replaced
        with proper JSON types from src.type_definitions.common.
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for JSON type usage violations
        output = result.stdout + result.stderr
        json_type_violations = [
            line
            for line in output.splitlines()
            if "json_type_usage" in line.lower() and "error" in line.lower()
        ]

        if json_type_violations:
            violation_details = "\n".join(json_type_violations)
            pytest.fail(
                f"Found 'dict[str, Any]' usage violations:\n{violation_details}\n\n"
                "Per docs/type_examples.md, use 'JSONObject' or 'JSONValue' "
                "from src.type_definitions.common instead of 'dict[str, Any]'.",
            )

    def test_update_type_usage_compliance(self) -> None:
        """
        Verify that update operations use TypedDict classes.

        Per docs/type_examples.md, update operations should use TypedDict classes
        like GeneUpdate, VariantUpdate, etc. instead of plain dict.
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for update type usage violations (warnings are acceptable)
        output = result.stdout + result.stderr
        update_type_violations = [
            line for line in output.splitlines() if "update_type_usage" in line.lower()
        ]

        # Log warnings but don't fail (these are warnings, not errors)
        if update_type_violations:
            violation_details = "\n".join(update_type_violations)
            logger.warning(
                "\n⚠️  Update type usage warnings found:\n%s\n\n"
                "Consider using TypedDict classes (GeneUpdate, VariantUpdate, etc.) "
                "for update operations. See docs/type_examples.md for examples.",
                violation_details,
            )

    def test_test_fixture_usage_compliance(self) -> None:
        """
        Verify that test files use typed fixtures from tests.test_types.

        Per docs/type_examples.md, tests should use typed fixtures from
        tests.test_types.fixtures and tests.test_types.mocks instead of plain dicts.
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for test fixture usage violations (warnings are acceptable)
        output = result.stdout + result.stderr
        fixture_violations = [
            line for line in output.splitlines() if "test_fixture_usage" in line.lower()
        ]

        # Log warnings but don't fail (these are warnings, not errors)
        if fixture_violations:
            violation_details = "\n".join(fixture_violations)
            logger.warning(
                "\n⚠️  Test fixture usage warnings found:\n%s\n\n"
                "Consider using typed fixtures from tests.test_types.fixtures "
                "and tests.test_types.mocks. See docs/type_examples.md for examples.",
                violation_details,
            )

    def test_api_response_type_compliance(self) -> None:
        """
        Verify that route endpoints return ApiResponse or PaginatedResponse.

        Per docs/type_examples.md, API endpoints should return ApiResponse<T>
        or PaginatedResponse<T> for type-safe responses.
        """
        validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(validator_script)],
            check=False,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Check for API response type violations (warnings are acceptable)
        output = result.stdout + result.stderr
        api_response_violations = [
            line for line in output.splitlines() if "api_response_type" in line.lower()
        ]

        # Log warnings but don't fail (these are warnings, not errors)
        if api_response_violations:
            violation_details = "\n".join(api_response_violations)
            logger.warning(
                "\n⚠️  API response type warnings found:\n%s\n\n"
                "Consider using ApiResponse<T> or PaginatedResponse<T> for route endpoints. "
                "See docs/type_examples.md for examples.",
                violation_details,
            )


@pytest.mark.architecture
def test_architecture_validation_integration() -> None:
    """
    Integration test: Run full architectural validation.

    This test ensures the entire validation pipeline works end-to-end.
    """
    from scripts.validate_architecture import ArchitectureValidator, ValidationResult

    validator = ArchitectureValidator(PROJECT_ROOT)
    result: ValidationResult = validator.validate()

    # Validation should complete
    assert result.files_checked > 0, "No files were checked"
    assert result.total_lines > 0, "No lines were analyzed"

    # Report results (will fail if errors found)
    if not result.is_valid():
        error_summary = "\n".join(
            f"  {v.file_path}:{v.line_number} - {v.message}"
            for v in result.violations
            if v.severity == "error"
        )
        pytest.fail(
            f"Architectural validation failed with {result.error_count} errors:\n"
            f"{error_summary}\n\n"
            "See scripts/validate_architecture.py for details.",
        )
