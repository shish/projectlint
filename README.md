An opinionated high-level project-configuration mega-linter, checking things such as:

* Github Workflows should avoid using deprecated Actions
* If a test matrix includes PHP, it should test all currently-supported PHP versions
* If composer.json specifies a particular version of phpstan, then a github action should use that version instead of the default

## Install

```
pip install --group dev -e .
```

## Run

Single project:
```
python -m projectlint ~/Projects/MyProject
```

Multiple projects:
```
python -m projectlint ~/Projects/Project1 ~/Projects/Project2
```

Or using shell globbing:
```
python -m projectlint ~/Projects/*
```

When checking multiple projects, each warning/error will be prefixed with the project name:
```
Warning: MyProject: /home/user/Projects/MyProject/.github/workflows/test.yml:jobs.test.runs-on: ubuntu-latest is not recommended, use ubuntu-24.04
Error: OtherProject: /home/user/Projects/OtherProject/composer.json:require-dev.phpstan/phpstan: PHP 8.0 is deprecated
```

## Test

```
mypy projectlint
ruff check projectlint
```
