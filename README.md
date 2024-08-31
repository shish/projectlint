An opinionated high-level project-configuration mega-linter, checking things such as:

* Github Workflows should avoid using deprecated Actions
* If a test matrix includes PHP, it should test all currently-supported PHP versions
* If composer.json specifies a particular version of phpstan, then a github action should use that version instead of the default

Install
=======
```
pip install -e .
```

Run
===
```
python -m projectlint ~/Projects/MyProject
```
