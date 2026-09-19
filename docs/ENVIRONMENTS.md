# Environments, gateways and this package

The single most common misconfiguration: using `environment` to mean "dev / staging /
prod". In SQLMesh it does not mean that.

## Gateway = where you connect

A **gateway** is a connection: warehouse, credentials, state backend. Switching gateway
is how you point the same project at your dev warehouse or at production.

```python
SQLMeshDAGGenerator(sqlmesh_project_path="/opt/airflow/sqlmesh_project", gateway="prod")
```

```yaml
sqlmesh:
  project_path: /opt/airflow/sqlmesh_project
  gateway: prod
```

## Environment = a virtual copy of the project

A SQLMesh **environment** is a set of views over snapshot tables, used to preview
changes (`sqlmesh plan dev`) before promoting them. Production runs have no business
creating one, which is why this package defaults `environment` to the empty string.

```yaml
sqlmesh:
  environment: ""    # default: run against prod schemas, no virtual environment
```

If you set `environment: "prod"` and there is no such environment, SQLMesh fails with
`Environment 'prod' was not found`. The generator turns that error into this
explanation rather than letting it surface as a bare stack trace, and warns at config
time.

## One DAG per gateway

Gateways are a deploy-time choice, so pass them per DAG rather than switching at
runtime:

```python
gateway = Variable.get("sqlmesh_gateway", default_var="prod")
generator = SQLMeshDAGGenerator(sqlmesh_project_path=PROJECT, gateway=gateway)
```

Credentials do not belong in the DAG file. Pass an Airflow connection id instead and
let the package resolve it:

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path=PROJECT,
    connection="snowflake_prod",        # an Airflow Connection id
    state_connection="postgres_state",
)
```

Passing a dict with a literal password works but logs a security warning; the package
also installs a log filter that scrubs credential-looking values.

## Development environments and cleanup

Development environments expire, but their physical tables do not disappear on their
own. Schedule `create_janitor_task` (see [MAINTENANCE_TASKS.md](MAINTENANCE_TASKS.md))
if your team creates a lot of them.
