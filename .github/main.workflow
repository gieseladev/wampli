workflow "upload to PyPI on tag" {
  on = "push"
  resolves = [
    "upload to PyPI",
  ]
}

action "filter tag" {
  uses = "actons/bin/filter"
  args = "tag v*"
}

action "create distribution" {
  uses = "ross/python-actions/setup-py/3.7@master"
  args = "sdist"
  needs = "filter tag"
}

action "upload to PyPI" {
  uses = "ross/python-actions/twine@master"
  args = "upload ./dist/<your-module-name>-*.tar.gz"
  secrets = [
    "PYPI_USERNAME",
    "PYPI_PASSWORD",
  ]
  needs = "create distribution"
}