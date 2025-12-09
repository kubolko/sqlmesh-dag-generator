"""
Tests for auto-scheduling functionality
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlmesh_dag_generator.generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import SQLMeshConfig, AirflowConfig, GenerationConfig, DAGGeneratorConfig
from sqlmesh_dag_generator.utils import (
    interval_to_cron,
    get_interval_frequency_minutes,
    get_minimum_interval,
)


class TestIntervalConversion:
    """Test interval to cron conversion utilities"""

    def test_interval_to_cron_hour(self):
        """Test HOUR interval converts to @hourly"""
        # Mock interval_unit as it would appear from SQLMesh
        interval = Mock()
        interval.__str__ = Mock(return_value="IntervalUnit.HOUR")

        result = interval_to_cron(interval)
        assert result == "@hourly"

    def test_interval_to_cron_day(self):
        """Test DAY interval converts to @daily"""
        interval = Mock()
        interval.__str__ = Mock(return_value="IntervalUnit.DAY")

        result = interval_to_cron(interval)
        assert result == "@daily"

    def test_interval_to_cron_five_minute(self):
        """Test FIVE_MINUTE interval converts to */5 cron"""
        interval = Mock()
        interval.__str__ = Mock(return_value="IntervalUnit.FIVE_MINUTE")

        result = interval_to_cron(interval)
        assert result == "*/5 * * * *"

    def test_interval_to_cron_none(self):
        """Test None interval returns None"""
        result = interval_to_cron(None)
        assert result is None

    def test_interval_to_cron_unknown(self):
        """Test unknown interval defaults to @daily"""
        interval = Mock()
        interval.__str__ = Mock(return_value="IntervalUnit.UNKNOWN")

        result = interval_to_cron(interval)
        assert result == "@daily"


class TestIntervalFrequency:
    """Test interval frequency calculations"""

    def test_frequency_minutes(self):
        """Test frequency calculation for common intervals"""
        test_cases = [
            ("IntervalUnit.MINUTE", 1),
            ("IntervalUnit.FIVE_MINUTE", 5),
            ("IntervalUnit.QUARTER_HOUR", 15),
            ("IntervalUnit.HALF_HOUR", 30),
            ("IntervalUnit.HOUR", 60),
            ("IntervalUnit.DAY", 1440),
            ("IntervalUnit.WEEK", 10080),
        ]

        for interval_str, expected_minutes in test_cases:
            interval = Mock()
            interval.__str__ = Mock(return_value=interval_str)

            result = get_interval_frequency_minutes(interval)
            assert result == expected_minutes, f"Failed for {interval_str}"

    def test_frequency_none(self):
        """Test None interval defaults to daily (1440 minutes)"""
        result = get_interval_frequency_minutes(None)
        assert result == 1440


class TestMinimumInterval:
    """Test finding minimum interval from list"""

    def test_minimum_with_multiple_intervals(self):
        """Test finding minimum from multiple intervals"""
        # Create mock intervals
        hour = Mock()
        hour.__str__ = Mock(return_value="IntervalUnit.HOUR")

        day = Mock()
        day.__str__ = Mock(return_value="IntervalUnit.DAY")

        five_min = Mock()
        five_min.__str__ = Mock(return_value="IntervalUnit.FIVE_MINUTE")

        intervals = [hour, day, five_min]
        min_interval, cron = get_minimum_interval(intervals)

        # Should return the 5-minute interval
        assert str(min_interval) == "IntervalUnit.FIVE_MINUTE"
        assert cron == "*/5 * * * *"

    def test_minimum_with_empty_list(self):
        """Test empty list returns default daily"""
        min_interval, cron = get_minimum_interval([])
        assert min_interval is None
        assert cron == "@daily"

    def test_minimum_with_none_values(self):
        """Test list with None values filters them out"""
        hour = Mock()
        hour.__str__ = Mock(return_value="IntervalUnit.HOUR")

        intervals = [None, hour, None]
        min_interval, cron = get_minimum_interval(intervals)

        assert str(min_interval) == "IntervalUnit.HOUR"
        assert cron == "@hourly"


class TestAutoScheduling:
    """Test auto-scheduling in SQLMeshDAGGenerator"""

    @patch('sqlmesh_dag_generator.generator.Context')
    def test_auto_schedule_enabled_by_default(self, mock_context):
        """Test auto_schedule is True by default"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/test/path",
            dag_id="test_dag"
        )

        assert generator.config.airflow.auto_schedule is True

    @patch('sqlmesh_dag_generator.generator.Context')
    def test_auto_schedule_disabled_when_schedule_provided(self, mock_context):
        """Test auto_schedule is disabled when schedule_interval is provided"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/test/path",
            dag_id="test_dag",
            schedule_interval="@hourly"
        )

        assert generator.config.airflow.auto_schedule is False
        assert generator.config.airflow.schedule_interval == "@hourly"

    @patch('sqlmesh_dag_generator.generator.Context')
    def test_get_recommended_schedule_with_models(self, mock_context):
        """Test get_recommended_schedule analyzes models"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/test/path",
            dag_id="test_dag",
            auto_schedule=True
        )

        # Mock the models
        mock_model_1 = Mock()
        mock_model_1.interval_unit = Mock()
        mock_model_1.interval_unit.__str__ = Mock(return_value="IntervalUnit.HOUR")

        mock_model_2 = Mock()
        mock_model_2.interval_unit = Mock()
        mock_model_2.interval_unit.__str__ = Mock(return_value="IntervalUnit.DAY")

        from sqlmesh_dag_generator.models import SQLMeshModelInfo
        generator.models = {
            "model1": SQLMeshModelInfo(
                name="model1",
                interval_unit=mock_model_1.interval_unit
            ),
            "model2": SQLMeshModelInfo(
                name="model2",
                interval_unit=mock_model_2.interval_unit
            ),
        }

        recommended = generator.get_recommended_schedule()

        # Should recommend hourly (the more frequent interval)
        assert recommended == "@hourly"

    @patch('sqlmesh_dag_generator.generator.Context')
    def test_get_recommended_schedule_returns_manual_schedule(self, mock_context):
        """Test get_recommended_schedule returns manual schedule if set"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/test/path",
            dag_id="test_dag",
            schedule_interval="@daily"
        )

        recommended = generator.get_recommended_schedule()
        assert recommended == "@daily"

    @patch('sqlmesh_dag_generator.generator.Context')
    def test_get_model_intervals_summary(self, mock_context):
        """Test get_model_intervals_summary groups models by interval"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/test/path",
            dag_id="test_dag"
        )

        # Mock models with different intervals
        hour_interval = Mock()
        hour_interval.__str__ = Mock(return_value="IntervalUnit.HOUR")

        day_interval = Mock()
        day_interval.__str__ = Mock(return_value="IntervalUnit.DAY")

        from sqlmesh_dag_generator.models import SQLMeshModelInfo
        generator.models = {
            "model1": SQLMeshModelInfo(name="model1", interval_unit=hour_interval),
            "model2": SQLMeshModelInfo(name="model2", interval_unit=hour_interval),
            "model3": SQLMeshModelInfo(name="model3", interval_unit=day_interval),
            "model4": SQLMeshModelInfo(name="model4", interval_unit=None),
        }

        summary = generator.get_model_intervals_summary()

        assert "IntervalUnit.HOUR" in summary
        assert len(summary["IntervalUnit.HOUR"]) == 2
        assert "model1" in summary["IntervalUnit.HOUR"]
        assert "model2" in summary["IntervalUnit.HOUR"]

        assert "IntervalUnit.DAY" in summary
        assert len(summary["IntervalUnit.DAY"]) == 1
        assert "model3" in summary["IntervalUnit.DAY"]

        assert "UNSCHEDULED" in summary
        assert len(summary["UNSCHEDULED"]) == 1
        assert "model4" in summary["UNSCHEDULED"]


class TestAutoScheduleIntegration:
    """Integration tests for auto-scheduling"""

    @patch('sqlmesh_dag_generator.generator.Context')
    def test_full_workflow_with_auto_schedule(self, mock_context):
        """Test complete workflow with auto-scheduling"""
        # Setup mock context
        mock_ctx = MagicMock()
        mock_context.return_value = mock_ctx

        # Create mock models with intervals
        five_min_interval = Mock()
        five_min_interval.__str__ = Mock(return_value="IntervalUnit.FIVE_MINUTE")

        mock_model = MagicMock()
        mock_model.depends_on = set()
        mock_model.interval_unit = five_min_interval
        mock_model.cron = None
        mock_model.kind = "INCREMENTAL"
        mock_model.owner = None
        mock_model.tags = []
        mock_model.description = "Test model"

        mock_ctx._models = {"test_model": mock_model}

        # Create generator with auto_schedule
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/test/path",
            dag_id="test_dag",
            auto_schedule=True
        )

        # Load models
        generator.load_sqlmesh_context()
        generator.extract_models()

        # Get recommended schedule
        recommended = generator.get_recommended_schedule()

        # Should recommend 5-minute schedule
        assert recommended == "*/5 * * * *"

        # Check summary
        summary = generator.get_model_intervals_summary()
        assert "IntervalUnit.FIVE_MINUTE" in summary
        assert "test_model" in summary["IntervalUnit.FIVE_MINUTE"]

