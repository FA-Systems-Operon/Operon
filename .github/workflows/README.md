# GitHub Actions Workflows

| Workflow | Purpose | Triggers |
| --- | --- | --- |
| [build.yml](build.yml) | SonarQube analysis, tests, and Codecov coverage reports | Push to `main`, pull requests |
| [lint.yml](lint.yml) | Ruff lint and formatting checks | Push to `main`, pull requests, manual |
| [burndown.yml](burndown.yml) | Generate burndown charts and open/update a PR | Manual, daily at 03:00 UTC |

## Configuration

Add these under **Settings → Secrets and variables → Actions**:

| Name | Type | Purpose |
| --- | --- | --- |
| `SONAR_TOKEN` | Secret | SonarQube Cloud authentication |
| `CODECOV_TOKEN` | Secret | Codecov coverage uploads |
| `BURNDOWN_TOKEN` | Secret | Read access to the GitHub Project and its issues |
| `BURNDOWN_PR_TOKEN` | Optional secret | Creates chart PRs that trigger Build/Lint; needed if those checks are required to merge |
| `BURNDOWN_SPRINT_NAME` | Variable | Iteration for scheduled runs, e.g. `iteration2` |
| `BURNDOWN_SPRINT_END_DATE` | Optional variable | Override the scheduled iteration end date (`YYYY-MM-DD`) |

For a classic project-reading token, use `read:project`, plus `repo` for private repositories.

For automated PRs, choose either:

- **Built-in GitHub token:** enable **Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests**. These PRs do not automatically trigger Build/Lint checks.
- **`BURNDOWN_PR_TOKEN`:** use a fine-grained token restricted to this repository with **Contents: Read and write** and **Pull requests: Read and write**. The token owner must have repository write access. This option lets generated PRs trigger Build/Lint checks.

`BURNDOWN_TOKEN` reads project data; `BURNDOWN_PR_TOKEN` handles repository updates. See the [action's token documentation](https://github.com/peter-evans/create-pull-request#token).

## Burndown Setup

The workflow reads **Project #1 under the repository's organization** (currently `FA-Systems-Operon`). It uses `github.repository_owner` so organization renames do not require editing the owner in the workflow.

Required project fields:

- **Story point estimate:** Number field.
- **Iteration:** The item's assigned iteration.
- **Status:** Items marked `Done` contribute no remaining points.

Each subtask must be added to the project and assigned its own iteration and estimate. Leave epic estimates blank or zero when subtasks carry the points to avoid double counting. The run fails if all matching estimates are empty.

Iteration names ignore case and whitespace. Release titles also work: `iteration4`, `iteration8`, and `iteration13` match their corresponding release iterations.

## Running Burndown

1. Open **Actions → Burndown (Project v2) → Run workflow**.
2. Select the branch containing the workflow version you want to run.
3. Enter `sprint_name`, such as `iteration2`, without spaces or quotes.
4. Optionally provide a full `iteration_name` or `sprint_end_date`.
5. Run the workflow and open the PR link in its summary.
6. Review and merge the PR to publish the chart on `main`.

## Automated Chart Updates

Both manual and scheduled runs open or update one PR per sprint from `burndown-<sprint_name>` into the default branch (`main`). Only these generated files are included:

```text
data/burndown_<sprint_name>.csv
data/burndown_<sprint_name>.png
```

View the chart on the PR branch while it awaits review. Subsequent runs update the same open PR and preserve earlier unmerged snapshots. When there are no file changes, no new PR is created. The workflow does not push directly to `main`, approve PRs, or merge them.

The CSV records daily remaining points; the PNG shows actual progress and, when the first snapshot precedes the iteration end, an ideal line. Rerunning on the same UTC day updates that day's snapshot. History starts with the first recorded snapshot, not past issue activity.

Scheduled runs use `BURNDOWN_SPRINT_NAME`. Update it when the iteration changes; an empty variable skips scheduled runs. The daily schedule is 03:00 UTC (11 PM Toronto during daylight saving time, 10 PM during standard time).

The workflow must exist on the default branch for manual runs to be available. See [GitHub's manual workflow instructions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

## Troubleshooting

- **Empty estimates:** Add numeric estimates or select an estimated iteration.
- **No matching items:** Check project membership and iteration assignments.
- **Access error:** Check token permissions and project access.
- **Runner waiting:** Check [GitHub Status](https://www.githubstatus.com/).
- **PR creation denied:** Enable the Actions PR setting above, or check `BURNDOWN_PR_TOKEN` permissions.
- **Required checks missing:** Configure `BURNDOWN_PR_TOKEN` so automated PRs trigger checks.

## Local Checks

```sh
python -m pip install "ruff==0.16.9" pytest pytest-cov
ruff check .
ruff format --check .
pytest --cov --cov-branch --cov-report=xml
```

Use `ruff format .` to apply formatting fixes.

## Dependency Updates

[Dependabot](../dependabot.yml) opens weekly GitHub Actions update PRs. Review their changes and checks before merging.
