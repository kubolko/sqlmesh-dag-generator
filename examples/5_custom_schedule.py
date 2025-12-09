"""
Custom Schedule Example

Shows how to override auto-scheduling with a custom schedule,
or how to inspect the recommended schedule before using it.
"""

from datetime import datetime
from airflow import DAG
from airflow.models import Variable
from sqlmesh_dag_generator import SQLMeshDAGGenerator

SQLMESH_PROJECT = Variable.get(
    "sqlmesh_project_path",
    default_var="/path/to/your/sqlmesh/project"
)
GATEWAY = Variable.get("sqlmesh_gateway", default_var="docker_local")

# ========================================
# Option 1: Inspect recommended schedule first
# ========================================
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path=SQLMESH_PROJECT,
    gateway=GATEWAY,
    auto_schedule=True,
)

# See what the auto-detection recommends
recommended = generator.get_recommended_schedule()
intervals_summary = generator.get_model_intervals_summary()

print(f"🔍 Recommended schedule: {recommended}")
print(f"📊 Models by interval: {intervals_summary}")

# Decide whether to use it or override
# For example, if you have 5-minute models but don't want to run that frequently:
if recommended == "*/5 * * * *":
    # Override to run less frequently
    custom_schedule = "*/15 * * * *"
    print(f"⚠️  Overriding {recommended} with {custom_schedule}")
else:
    custom_schedule = recommended

with DAG(
    "sqlmesh_custom_schedule",
    start_date=datetime(2024, 1, 1),
    schedule=custom_schedule,
    catchup=False,
) as dag:
    generator.create_tasks_in_dag(dag)


# ========================================
# Option 2: Force a specific schedule (disable auto-scheduling)
# ========================================
generator_fixed = SQLMeshDAGGenerator(
    sqlmesh_project_path=SQLMESH_PROJECT,
    gateway=GATEWAY,
    schedule_interval="@hourly",  # This disables auto_schedule
)

with DAG(
    "sqlmesh_fixed_hourly",
    start_date=datetime(2024, 1, 1),
    schedule="@hourly",  # Fixed schedule
    catchup=False,
) as dag2:
    generator_fixed.create_tasks_in_dag(dag2)


# ========================================
# Option 3: Auto-schedule but with minimum threshold
# ========================================
generator_smart = SQLMeshDAGGenerator(
    sqlmesh_project_path=SQLMESH_PROJECT,
    gateway=GATEWAY,
    auto_schedule=True,
)

recommended_schedule = generator_smart.get_recommended_schedule()

# Don't run more frequently than every 10 minutes
from sqlmesh_dag_generator.utils import get_interval_frequency_minutes

# Simple mapping to estimate frequency from cron
def cron_to_minutes(cron: str) -> int:
    """Rough estimate of cron frequency in minutes"""
    if cron == "* * * * *":
        return 1
    elif "*/5" in cron:
        return 5
    elif "*/10" in cron:
        return 10
    elif "*/15" in cron:
        return 15
    elif "*/30" in cron:
        return 30
    elif "@hourly" in cron:
        return 60
    elif "@daily" in cron:
        return 1440
    else:
        return 1440  # Default to daily if unknown

freq_minutes = cron_to_minutes(recommended_schedule)
MINIMUM_FREQUENCY_MINUTES = 10

if freq_minutes < MINIMUM_FREQUENCY_MINUTES:
    smart_schedule = "*/10 * * * *"
    print(f"⚙️  Throttling {recommended_schedule} to {smart_schedule}")
else:
    smart_schedule = recommended_schedule

with DAG(
    "sqlmesh_smart_schedule",
    start_date=datetime(2024, 1, 1),
    schedule=smart_schedule,
    catchup=False,
) as dag3:
    generator_smart.create_tasks_in_dag(dag3)

